"""M3 报名路由 + 二维码（§2.5、§3.4、§5.5）。"""

from __future__ import annotations

import io
import logging

import qrcode
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import build_page, clamp_page, get_db, iso_z
from app.deps import (
    assert_activity_owner,
    get_activity_or_404,
    get_current_user,
    require_student,
)
from app.errors import BadRequest, Forbidden, NotFound, ok
from app.models import Activity, Registration, RegistrationStatus, User
from app.schemas import MyRegistrationOut, RegistrationCreate
from app.services.registration import cancel_or_withdraw, my_registrations, signup

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["registrations"])


@router.post("/activities/{activity_id}/registrations")
def create_registration(
    activity_id: int,
    payload: RegistrationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    activity = get_activity_or_404(db, activity_id)
    registration = signup(db, activity, user, payload.accept_waitlist)
    return ok(
        {
            "id": registration.id,
            "activity_id": registration.activity_id,
            "user_id": registration.user_id,
            "username": user.username,
            "real_name": user.real_name,
            "status": str(registration.status),
            "accept_waitlist": bool(registration.accept_waitlist),
            "lottery_rank": registration.lottery_rank,
            "checked_in_at": None,
            "created_at": iso_z(registration.created_at),
        },
        message="报名成功",
    )


@router.delete("/activities/{activity_id}/registrations/me")
def cancel_registration(
    activity_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    activity = get_activity_or_404(db, activity_id)
    return ok(cancel_or_withdraw(db, activity, user))


@router.get("/me/registrations")
def list_my_registrations(
    page: int = Query(default=1),
    size: int = Query(default=10),
    db: Session = Depends(get_db),
    user: User = Depends(require_student),
):
    page, size = clamp_page(page, size)
    rows, total = my_registrations(db, user, page, size)
    items = [
        MyRegistrationOut(
            id=registration.id,
            status=str(registration.status),
            lottery_rank=registration.lottery_rank,
            qr_available=str(registration.status) == "WON" and bool(registration.qr_token),
            checked_in=registration.checkin is not None,
            accept_waitlist=bool(registration.accept_waitlist),
            created_at=registration.created_at,
            activity=registration.activity,
        ).model_dump(mode="json")
        for registration in rows
    ]
    return ok(build_page(items, total, page, size))


@router.get("/registrations/{registration_id}/qrcode")
def registration_qrcode(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    registration = db.get(Registration, registration_id)
    if registration is None:
        raise NotFound("报名记录不存在")

    activity = db.get(Activity, registration.activity_id)
    if user.id != registration.user_id:  # 非本人：仅该活动组织者或 ADMIN（§5.5）
        if activity is None:
            raise NotFound("活动不存在")
        assert_activity_owner(activity, user)

    if str(registration.status) != "WON" or not registration.qr_token:
        raise BadRequest("签到码尚未生成或已失效，仅中签者可查看")

    content = f"{get_settings().PUBLIC_BASE_URL}/checkin.html?code={registration.qr_token}"
    image = qrcode.QRCode(box_size=8, border=2)
    image.add_data(content)
    image.make(fit=True)
    buffer = io.BytesIO()
    image.make_image(fill_color="black", back_color="white").save(buffer, format="PNG")
    return Response(
        content=buffer.getvalue(),
        media_type="image/png",
        headers={"Cache-Control": "no-store"},
    )
