"""M3 报名 / 取消退出 / 我的报名（§2.5）。"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.database import as_utc, retry_on_locked, utcnow
from app.errors import BadRequest, Conflict, NotFound
from app.models import Activity, Registration, RegistrationStatus, Role
from app.services.lottery import promote_waitlist

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (
    RegistrationStatus.PENDING,
    RegistrationStatus.WON,
    RegistrationStatus.WAITING,
    RegistrationStatus.LOST,
)


def _assert_signup_open(activity: Activity) -> None:
    status = str(activity.status)
    if status == "CANCELLED":
        raise BadRequest("活动已取消，不能报名")
    if status != "PUBLISHED":
        raise BadRequest("当前活动状态不允许报名")
    if utcnow() >= as_utc(activity.signup_deadline):
        raise BadRequest("报名已截止")


@retry_on_locked()
def signup(db, activity: Activity, user, accept_waitlist: bool) -> Registration:
    if str(user.role) != Role.STUDENT.value:
        from app.errors import Forbidden

        raise Forbidden("仅学生可以报名活动")

    _assert_signup_open(activity)

    existing = db.scalar(
        select(Registration).where(
            Registration.activity_id == activity.id, Registration.user_id == user.id
        )
    )
    if existing is not None and str(existing.status) != "CANCELLED":
        raise Conflict("您已报名该活动，请勿重复报名")

    if existing is not None:  # 取消后重报：复用原记录，保留 created_at
        existing.status = RegistrationStatus.PENDING
        existing.accept_waitlist = accept_waitlist
        existing.lottery_rank = None
        existing.qr_token = None
        existing.updated_at = utcnow()
        registration = existing
    else:
        registration = Registration(
            activity_id=activity.id,
            user_id=user.id,
            status=RegistrationStatus.PENDING,
            accept_waitlist=accept_waitlist,
        )
        db.add(registration)

    try:
        db.commit()
    except IntegrityError as exc:  # 并发双击兜底
        db.rollback()
        logger.warning("[registration] 唯一约束冲突 activity_id=%s user_id=%s", activity.id, user.id)
        raise Conflict("您已报名该活动，请勿重复报名") from exc
    db.refresh(registration)
    return registration


def cancel_or_withdraw(db, activity: Activity, user) -> dict:
    """取消/退出统一入口，按当前状态分流（§2.5-4）。"""
    registration = db.scalar(
        select(Registration).where(
            Registration.activity_id == activity.id, Registration.user_id == user.id
        )
    )
    if registration is None:
        raise NotFound("未找到您的报名记录")

    status = str(registration.status)
    if status in ("CANCELLED", "WITHDRAWN"):
        raise BadRequest("当前报名状态不可取消")

    if status in ("PENDING", "WAITING", "LOST"):
        registration.status = RegistrationStatus.CANCELLED
        registration.updated_at = utcnow()
        promoted = 0
    else:  # WON
        registration.status = RegistrationStatus.WITHDRAWN
        registration.qr_token = None
        registration.updated_at = utcnow()
        promoted = len(promote_waitlist(db, activity))  # I-3：同事务递补

    db.commit()
    logger.info(
        "[registration] 取消/退出 activity_id=%s user_id=%s from=%s to=%s promoted=%s",
        activity.id,
        user.id,
        status,
        str(registration.status),
        promoted,
    )
    return {"status": str(registration.status), "promoted": promoted}


def get_registration_for_view(db, activity_id: int, user_id: int) -> Registration | None:
    return db.scalar(
        select(Registration)
        .options(joinedload(Registration.checkin), joinedload(Registration.activity))
        .where(Registration.activity_id == activity_id, Registration.user_id == user_id)
    )


def my_registrations(db, user, page: int, size: int) -> tuple[list[Registration], int]:
    filters = [Registration.user_id == user.id, Registration.status != RegistrationStatus.CANCELLED]
    total = db.scalar(select(func.count(Registration.id)).where(*filters)) or 0
    rows = db.scalars(
        select(Registration)
        .options(joinedload(Registration.activity), joinedload(Registration.checkin))
        .where(*filters)
        .order_by(Registration.created_at.desc(), Registration.id.desc())
        .offset((page - 1) * size)
        .limit(size)
    ).unique().all()
    return rows, total
