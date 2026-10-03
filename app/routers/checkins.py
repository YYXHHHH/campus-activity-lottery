"""M6 签到路由（§3.5）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db, iso_z
from app.deps import assert_activity_owner, get_activity_or_404, require_organizer
from app.errors import ok
from app.models import User
from app.schemas import CheckinIn, ManualCheckinIn
from app.services.checkin import do_checkin, manual_checkin

router = APIRouter(prefix="/api", tags=["checkins"])


def _result(checkin, registration) -> dict:
    return {
        "user_name": registration.user.real_name,
        "username": registration.user.username,
        "checked_in_at": iso_z(checkin.checked_in_at),
        "method": str(checkin.method),
    }


@router.post("/activities/{activity_id}/checkin")
def scan_checkin(
    activity_id: int,
    payload: CheckinIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    return ok(_result(*do_checkin(db, activity, payload.code, user)))


@router.post("/activities/{activity_id}/checkin/manual")
def manual_checkin_route(
    activity_id: int,
    payload: ManualCheckinIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_organizer),
):
    activity = get_activity_or_404(db, activity_id)
    assert_activity_owner(activity, user)
    return ok(_result(*manual_checkin(db, activity, payload.username, user)))
