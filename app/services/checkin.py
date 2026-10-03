"""M6 签到校验链。"""

from __future__ import annotations

import logging
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.database import as_utc, iso_z, retry_on_locked, utcnow
from app.errors import BadRequest, Conflict, NotFound
from app.models import Activity, Checkin, CheckinMethod, Registration, RegistrationStatus, User

logger = logging.getLogger(__name__)


def normalize_code(raw: str | None) -> str:
    """支持直接传码或传完整二维码 URL。"""
    text = (raw or "").strip()
    if not text:
        raise BadRequest("签到码不能为空")
    if "code=" in text:
        query = urlparse(text).query or text.split("?", 1)[-1]
        values = parse_qs(query).get("code") or []
        text = values[0].strip() if values else ""
        if not text:
            raise BadRequest("签到码不能为空")
    return text


def _already_checked_in(registration: Registration, checkin: Checkin) -> Conflict:
    # SQLite 读回的是 naive 值，必须先按 UTC 还原再转本地时区，否则提示会显示 UTC 墙上时间
    checked_local = as_utc(checkin.checked_in_at).astimezone()
    return Conflict(
        f"该同学已于 {checked_local.strftime('%H:%M')} 签到",
        data={
            "user_name": registration.user.real_name,
            "username": registration.user.username,
            "checked_in_at": iso_z(checkin.checked_in_at),
        },
    )


def _guard_activity_checkinable(activity: Activity) -> None:
    status = str(activity.status)
    if status == "CANCELLED":
        raise BadRequest("活动已取消，不能签到")
    if status == "PUBLISHED":
        raise BadRequest("活动尚未抽签，不能签到")
    if status == "DRAFT":
        raise BadRequest("活动尚未发布，不能签到")


def _record(db, activity: Activity, registration: Registration, operator: User, method: str, code: str | None):
    existing = db.scalar(select(Checkin).where(Checkin.registration_id == registration.id))
    if existing is not None:
        raise _already_checked_in(registration, existing)

    checkin = Checkin(
        registration_id=registration.id,
        activity_id=activity.id,
        user_id=registration.user_id,
        operator_id=operator.id,
        checkin_code=(code or "")[:64] or None,
        method=method,
        checked_in_at=utcnow(),
    )
    db.add(checkin)
    try:
        db.commit()
    except IntegrityError as exc:  # 并发重复签到由 UNIQUE 兜底
        db.rollback()
        again = db.scalar(select(Checkin).where(Checkin.registration_id == registration.id))
        if again is None:
            raise
        raise _already_checked_in(registration, again) from exc
    db.refresh(checkin)
    logger.info(
        "[checkin] 签到成功 activity_id=%s user_id=%s operator_id=%s method=%s",
        activity.id,
        registration.user_id,
        operator.id,
        method,
    )
    return checkin, registration


@retry_on_locked()
def do_checkin(db, activity: Activity, code: str | None, operator: User, method: str = CheckinMethod.SCAN):
    _guard_activity_checkinable(activity)
    token = normalize_code(code)

    registration = db.scalar(
        select(Registration)
        .options(joinedload(Registration.user), joinedload(Registration.checkin))
        .where(Registration.qr_token == token)
    )
    if registration is None:
        raise NotFound("签到码无效")
    if registration.activity_id != activity.id:
        raise BadRequest("签到码不属于本活动")
    if str(registration.status) != RegistrationStatus.WON.value:
        raise BadRequest("该同学当前不是中签状态")

    return _record(db, activity, registration, operator, str(method), token)


@retry_on_locked()
def manual_checkin(db, activity: Activity, username: str, operator: User):
    _guard_activity_checkinable(activity)
    name = (username or "").strip()
    if not name:
        raise BadRequest("学号/工号不能为空")

    registration = db.scalar(
        select(Registration)
        .options(joinedload(Registration.user), joinedload(Registration.checkin))
        .join(User, User.id == Registration.user_id)
        .where(Registration.activity_id == activity.id, User.username == name)
    )
    if registration is None:
        raise BadRequest("该同学未报名本活动")
    if str(registration.status) != RegistrationStatus.WON.value:
        raise BadRequest("该同学当前不是中签状态")

    return _record(db, activity, registration, operator, CheckinMethod.MANUAL.value, None)
