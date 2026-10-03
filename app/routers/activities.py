"""M2 活动管理 + M7 统计/导出路由。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.database import as_utc, build_page, clamp_page, get_db, iso_z, utcnow
from app.deps import (
    assert_activity_owner,
    get_activity_or_404,
    get_current_user,
    require_organizer,
)
from app.errors import BadRequest, Forbidden, ok
from app.models import (
    ACTIVITY_STATUS_CN,
    Activity,
    ActivityStatus,
    Checkin,
    Registration,
    RegistrationStatus,
    Role,
    User,
)
from app.schemas import (
    ActivityCreate,
    ActivityDetailOut,
    ActivityOut,
    ActivityUpdate,
    UserBrief,
    WinRow,
)
from app.services.exporter import build_workbook, content_disposition
from app.services.lottery import promote_waitlist, run_lottery
from app.services.stats import calc_stats

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["activities"])

STUDENT_VISIBLE = {"PUBLISHED", "LOTTERY_DONE"}
ACTIVE_REG_STATUSES = ("PENDING", "WON", "WAITING", "LOST", "WITHDRAWN")


def _is_admin(user: User) -> bool:
    return str(user.role) == Role.ADMIN.value


def _validate_time_fields(*, start_time, signup_deadline, now, require_future: bool) -> None:
    if require_future and not as_utc(signup_deadline) > now:
        raise BadRequest("报名截止时间必须晚于当前时间")
    if as_utc(signup_deadline) > as_utc(start_time):
        raise BadRequest("报名截止时间不能晚于活动开始时间")


def _registration_brief(db: Session, activity_id: int, user_id: int) -> dict | None:
    registration = db.scalar(
        select(Registration)
        .options(joinedload(Registration.checkin))
        .where(Registration.activity_id == activity_id, Registration.user_id == user_id)
    )
    if registration is None or str(registration.status) == "CANCELLED":
        return None
    return {
        "id": registration.id,
        "status": str(registration.status),
        "lottery_rank": registration.lottery_rank,
        "qr_available": bool(registration.qr_token) and str(registration.status) == "WON",
        "accept_waitlist": bool(registration.accept_waitlist),
        "checked_in": registration.checkin is not None,
    }


def _active_registration_count(db: Session, activity_id: int) -> int:
    return (
        db.scalar(
            select(func.count(Registration.id)).where(
                Registration.activity_id == activity_id,
                Registration.status.in_(ACTIVE_REG_STATUSES),
            )
        )
        or 0
    )


# ---------------- 创建 / 列表 / 详情 ----------------
@router.post("/activities")
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    now = utcnow()
    _validate_time_fields(
        start_time=payload.start_time, signup_deadline=payload.signup_deadline, now=now, require_future=True
    )

    activity = Activity(
        organizer_id=user.id,
        title=payload.title,
        description=payload.description,
        location=payload.location,
        start_time=payload.start_time,
        end_time=payload.end_time,
        signup_deadline=payload.signup_deadline,
        quota=payload.quota,
        status=ActivityStatus(payload.status),
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    return ok(ActivityOut.model_validate(activity).model_dump(mode="json"))


@router.get("/activities")
def list_activities(
    status: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    mine: bool = Query(default=False),
    page: int = Query(default=1),
    size: int = Query(default=10),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    page, size = clamp_page(page, size)
    filters = []

    if mine:
        if str(user.role) == Role.STUDENT.value:
            raise Forbidden("仅组织者或管理员可查看自己创建的活动")
        if not _is_admin(user):
            filters.append(Activity.organizer_id == user.id)
    elif str(user.role) == Role.STUDENT.value:
        if status is not None and status not in STUDENT_VISIBLE:
            raise BadRequest("学生仅可查看报名中或已抽签的活动")
        filters.append(Activity.status.in_(STUDENT_VISIBLE))
    elif status is not None:
        filters.append(Activity.status == status)

    if keyword:
        like = f"%{keyword[:50]}%"
        filters.append(or_(Activity.title.like(like), Activity.location.like(like)))

    total = db.scalar(select(func.count(Activity.id)).where(*filters)) or 0
    rows = db.scalars(
        select(Activity)
        .where(*filters)
        .order_by(Activity.created_at.desc(), Activity.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).all()
    items = [ActivityOut.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(build_page(items, total, page, size))


@router.get("/activities/{activity_id}")
def get_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    activity = get_activity_or_404(db, activity_id)

    # 兜底 I-2：读时发现到期未抽签，同步触发幂等抽签
    if str(activity.status) == "PUBLISHED" and utcnow() >= as_utc(activity.signup_deadline):
        run_lottery(db, activity.id)
        db.refresh(activity)

    if str(activity.status) == "DRAFT" and not (assert_activity_owner_allowed(activity, user)):
        raise Forbidden("无权限访问该资源")

    detail = ActivityDetailOut.model_validate(activity).model_dump(mode="json")
    detail["my_registration"] = _registration_brief(db, activity.id, user.id)
    detail["registered_count"] = _active_registration_count(db, activity.id)
    detail["lottery_status_cn"] = ACTIVITY_STATUS_CN.get(str(activity.status), str(activity.status))
    return ok(detail)


def assert_activity_owner_allowed(activity: Activity, user: User) -> bool:
    """只读判断归属，不抛异常（用于 DRAFT 可见性）。"""
    return _is_admin(user) or activity.organizer_id == user.id


# ---------------- 编辑 / 发布 / 取消 / 抽签 ----------------
@router.patch("/activities/{activity_id}")
def edit_activity(
    activity_id: int,
    payload: ActivityUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)

    status = str(activity.status)
    now = utcnow()
    if status in ("LOTTERY_DONE", "CANCELLED"):
        raise BadRequest("抽签已完成或活动已取消，不可编辑")
    if status == "PUBLISHED" and now >= as_utc(activity.signup_deadline):
        raise BadRequest("报名已截止，不可编辑")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise BadRequest("没有需要修改的字段")

    new_deadline = as_utc(changes.get("signup_deadline")) if changes.get("signup_deadline") else as_utc(activity.signup_deadline)
    new_start = as_utc(changes.get("start_time")) if changes.get("start_time") else as_utc(activity.start_time)
    # PUBLISHED 允许把截止时间改为过去；DRAFT 仍须晚于当前
    _validate_time_fields(
        start_time=new_start,
        signup_deadline=new_deadline,
        now=now,
        require_future=status == "DRAFT",
    )

    if "quota" in changes and changes["quota"] is not None:
        won_count = (
            db.scalar(
                select(func.count(Registration.id)).where(
                    Registration.activity_id == activity.id,
                    Registration.status == RegistrationStatus.WON,
                )
            )
            or 0
        )
        if changes["quota"] < won_count:  # S10
            raise BadRequest(f"名额不能少于当前中签人数（{won_count} 人）")

    for field, value in changes.items():
        setattr(activity, field, value)
    activity.updated_at = now

    promoted = 0
    if status == "PUBLISHED" and "quota" in changes:
        promoted = len(promote_waitlist(db, activity))  # I-4：同事务递补

    db.commit()
    db.refresh(activity)
    data = ActivityOut.model_validate(activity).model_dump(mode="json")
    data["promoted"] = promoted
    return ok(data)


@router.post("/activities/{activity_id}/publish")
def publish_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    if str(activity.status) != "DRAFT":
        raise BadRequest("仅草稿状态的活动可以发布")
    if utcnow() >= as_utc(activity.signup_deadline):
        raise BadRequest("报名截止时间已过，不可发布")
    activity.status = ActivityStatus.PUBLISHED
    activity.updated_at = utcnow()
    db.commit()
    return ok({"status": str(activity.status)})


@router.post("/activities/{activity_id}/cancel")
def cancel_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    if str(activity.status) == "CANCELLED":
        raise BadRequest("活动已是取消状态")
    activity.status = ActivityStatus.CANCELLED
    activity.updated_at = utcnow()
    db.commit()
    return ok({"status": str(activity.status)})


@router.post("/activities/{activity_id}/lottery")
def manual_lottery(
    activity_id: int,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    result = run_lottery(db, activity.id, force=force and _is_admin(user))
    return ok(result)


# ---------------- 名单 / 签到 / 统计 / 导出 ----------------
@router.get("/activities/{activity_id}/registrations")
def list_registrations(
    activity_id: int,
    status: str | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=10),
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    page, size = clamp_page(page, size)

    filters = [Registration.activity_id == activity.id]
    if status:
        filters.append(Registration.status == status)
    else:
        filters.append(Registration.status != RegistrationStatus.CANCELLED)

    total = db.scalar(select(func.count(Registration.id)).where(*filters)) or 0
    rows = db.scalars(
        select(Registration)
        .options(joinedload(Registration.user), joinedload(Registration.checkin))
        .where(*filters)
        .order_by(Registration.id.asc())
        .offset((page - 1) * size)
        .limit(size)
    ).unique().all()

    items = []
    for registration in rows:
        related_user = registration.user
        items.append(
            {
                "id": registration.id,
                "activity_id": registration.activity_id,
                "user_id": registration.user_id,
                "username": related_user.username,
                "real_name": related_user.real_name,
                "status": str(registration.status),
                "accept_waitlist": bool(registration.accept_waitlist),
                "lottery_rank": registration.lottery_rank,
                "checked_in_at": (
                    iso_z(registration.checkin.checked_in_at) if registration.checkin else None
                ),
                "created_at": iso_z(registration.created_at),
            }
        )
    return ok(build_page(items, total, page, size))


@router.get("/activities/{activity_id}/winners")
def list_winners(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)

    def _rows(target_status: RegistrationStatus):
        rows = db.scalars(
            select(Registration)
            .options(joinedload(Registration.user), joinedload(Registration.checkin))
            .where(Registration.activity_id == activity.id, Registration.status == target_status)
            .order_by(Registration.lottery_rank.asc())
        ).all()
        return [
            WinRow(
                registration_id=registration.id,
                user=UserBrief.model_validate(registration.user),
                lottery_rank=registration.lottery_rank,
                checked_in=registration.checkin is not None,
            ).model_dump(mode="json")
            for registration in rows
        ]

    return ok({"winners": _rows(RegistrationStatus.WON), "waitlist": _rows(RegistrationStatus.WAITING)})


@router.get("/activities/{activity_id}/checkins")
def list_checkins(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)

    winners = db.scalars(
        select(Registration)
        .options(joinedload(Registration.user), joinedload(Registration.checkin))
        .where(Registration.activity_id == activity.id, Registration.status == RegistrationStatus.WON)
    ).all()

    checked_in, not_checked_in = [], []
    for registration in winners:
        payload = {
            "registration_id": registration.id,
            "user": UserBrief.model_validate(registration.user).model_dump(mode="json"),
            "lottery_rank": registration.lottery_rank,
            "checked_in_at": iso_z(registration.checkin.checked_in_at) if registration.checkin else None,
            "method": str(registration.checkin.method) if registration.checkin else None,
        }
        (checked_in if registration.checkin else not_checked_in).append(payload)

    checked_in.sort(key=lambda row: row["checked_in_at"] or "")
    return ok({"checked_in": checked_in, "not_checked_in": not_checked_in})


@router.get("/activities/{activity_id}/stats")
def activity_stats(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    return ok(calc_stats(db, activity))


@router.get("/activities/{activity_id}/export")
def export_activity(
    activity_id: int,
    type: str = Query(default="all", pattern="^(all|winners)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    content, filename = build_workbook(db, activity, type)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": content_disposition(filename), "Cache-Control": "no-store"},
    )

