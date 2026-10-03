"""M1 认证与用户。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.errors import Conflict, LoginFailed, Unauthorized, ok
from app.models import Role, User
from app.schemas import LoginIn, RegisterIn, UserOut
from app.security import create_access_token, hash_password, verify_password

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register")
def register(payload: RegisterIn, db: Session = Depends(get_db)):
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        role=payload.role,
        email=payload.email,
        phone=payload.phone,
        is_active=1,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("用户名已存在") from exc
    db.refresh(user)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))


@router.post("/login")
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        logger.debug("[auth] 登录失败 username=%s", payload.username)
        raise LoginFailed("用户名或密码错误")
    if not user.is_active:
        raise Unauthorized("账号已被禁用")

    token, expires_in = create_access_token(user)
    return ok(
        {
            "access_token": token,
            "token_type": "bearer",
            "expires_in": expires_in,
            "user": {"id": user.id, "username": user.username, "real_name": user.real_name, "role": str(user.role)},
        }
    )


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return ok(UserOut.model_validate(user).model_dump(mode="json"))
