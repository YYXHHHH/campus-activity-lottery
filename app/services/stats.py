"""M7 统计计算。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.database import iso_z
from app.models import Activity, Checkin, Registration, RegistrationStatus


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 0
    return round(numerator / denominator, 4)


def calc_stats(db, activity: Activity) -> dict:
    rows = db.execute(
        select(Registration.status, func.count(Registration.id))
        .where(Registration.activity_id == activity.id)
        .group_by(Registration.status)
    ).all()
    counts = {str(status): 0 for status in RegistrationStatus}
    for status, count in rows:
        counts[str(status)] = count

    checked_in = (
        db.scalar(select(func.count(Checkin.id)).where(Checkin.activity_id == activity.id)) or 0
    )
    registered = sum(
        counts[key] for key in ("PENDING", "WON", "WAITING", "LOST", "WITHDRAWN")
    )
    won = counts["WON"]

    return {
        "activity_id": activity.id,
        "quota": activity.quota,
        "registered": registered,
        "pending": counts["PENDING"],
        "won": won,
        "waiting": counts["WAITING"],
        "lost": counts["LOST"],
        "withdrawn": counts["WITHDRAWN"],
        "cancelled": counts["CANCELLED"],
        "checked_in": checked_in,
        "win_rate": _ratio(won, registered),
        "checkin_rate": _ratio(checked_in, won),
        "quota_usage": _ratio(won, activity.quota),
        "lottery_at": iso_z(activity.lottery_at) if activity.lottery_at else None,
    }
