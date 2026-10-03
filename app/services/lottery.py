"""M4 抽签 + M5 候补递补（§5.2、§5.3）。"""

from __future__ import annotations

import logging
import random
import secrets

from sqlalchemy import func, select, update

from app.database import as_utc, utcnow
from app.errors import BadRequest, NotFound
from app.models import Activity, Registration, RegistrationStatus

logger = logging.getLogger(__name__)


def _count_by_status(db, activity_id: int) -> dict[str, int]:
    rows = db.execute(
        select(Registration.status, func.count(Registration.id)).where(
            Registration.activity_id == activity_id
        ).group_by(Registration.status)
    ).all()
    counts = {str(status): 0 for status in RegistrationStatus}
    for status, count in rows:
        counts[str(status)] = count
    return counts


def run_lottery(db, activity_id: int, *, force: bool = False) -> dict:
    """抽签唯一入口：幂等、随机、可复现（§5.2）。"""
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise NotFound("活动不存在")

    status = str(activity.status)
    if status == "CANCELLED":
        raise BadRequest("活动已取消，无法抽签")
    if status == "LOTTERY_DONE":
        counts = _count_by_status(db, activity_id)
        return {
            "executed": False,
            "reason": "already_done",
            "won": counts["WON"],
            "waiting": counts["WAITING"],
            "lost": counts["LOST"],
        }
    if status != "PUBLISHED":
        raise BadRequest("仅报名中的活动可以抽签")
    if not force and utcnow() < as_utc(activity.signup_deadline):
        raise BadRequest("报名尚未截止，不能抽签")

    seed = secrets.token_hex(16)
    rows = db.execute(
        update(Activity)
        .where(Activity.id == activity_id, Activity.status == "PUBLISHED")
        .values(status="LOTTERY_DONE", lottery_seed=seed, lottery_at=utcnow())
    ).rowcount
    if rows == 0:
        db.rollback()
        counts = _count_by_status(db, activity_id)
        return {
            "executed": False,
            "reason": "concurrent_or_done",
            "won": counts["WON"],
            "waiting": counts["WAITING"],
            "lost": counts["LOST"],
        }

    pending = db.scalars(
        select(Registration)
        .where(Registration.activity_id == activity_id, Registration.status == RegistrationStatus.PENDING)
        .order_by(Registration.id)
    ).all()

    shuffled = list(pending)
    random.Random(seed).shuffle(shuffled)

    won = waiting = lost = 0
    for index, registration in enumerate(shuffled, start=1):
        registration.lottery_rank = index
        if index <= activity.quota:
            registration.status = RegistrationStatus.WON
            registration.qr_token = secrets.token_urlsafe(16)
            won += 1
        elif registration.accept_waitlist:
            registration.status = RegistrationStatus.WAITING
            waiting += 1
        else:
            registration.status = RegistrationStatus.LOST
            lost += 1

    db.commit()
    logger.info(
        "[lottery] 抽签完成 activity_id=%s seed=%s won=%s waiting=%s lost=%s",
        activity_id,
        seed,
        won,
        waiting,
        lost,
    )
    return {"executed": True, "reason": None, "won": won, "waiting": waiting, "lost": lost}


def promote_waitlist(db, activity: Activity) -> list[Registration]:
    """按 lottery_rank 升序补足名额；不 commit、不 rollback，事务控制权归调用方（§5.3）。"""
    db.flush()  # 先落盘调用方在本次事务中的状态变更，再统计 WON，避免读到过期计数
    won_count = db.scalar(
        select(func.count(Registration.id)).where(
            Registration.activity_id == activity.id, Registration.status == RegistrationStatus.WON
        )
    )
    vacancy = activity.quota - (won_count or 0)
    if vacancy <= 0:
        return []

    order_by_rank = (
        select(Registration)
        .where(Registration.activity_id == activity.id, Registration.status == RegistrationStatus.WAITING)
        .order_by(Registration.lottery_rank.asc())
        .limit(vacancy)
    )
    if db.bind.dialect.name == "mysql":
        order_by_rank = order_by_rank.with_for_update()
    candidates = db.scalars(order_by_rank).all()

    for registration in candidates:
        registration.status = RegistrationStatus.WON
        registration.qr_token = secrets.token_urlsafe(16)
    db.flush()

    if candidates:
        logger.info(
            "[lottery] 候补递补 activity_id=%s promoted_user_ids=%s count=%s",
            activity.id,
            [registration.user_id for registration in candidates],
            len(candidates),
        )
    return candidates
