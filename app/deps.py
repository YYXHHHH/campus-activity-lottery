"""M0 依赖注入：当前用户 / 角色 / 活动归属。"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.errors import Forbidden, NotFound, Unauthorized
from app.models import Activity, Role, User
from app.security import TokenError, decode_token


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    header = request.headers.get("Authorization") or ""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise Unauthorized("未登录或登录已失效")
    try:
        user_id = decode_token(token.strip())
    except TokenError:
        raise Unauthorized("登录状态已失效，请重新登录") from None
    user = db.get(User, user_id)
    if user is None:
        raise Unauthorized("登录状态已失效，请重新登录")
    if not user.is_active:
        raise Unauthorized("账号已被禁用")
    return user


def require_role(*roles: str):
    allowed = {str(role) for role in roles}

    def dependency(user: User = Depends(get_current_user)) -> User:
        if str(user.role) not in allowed:
            raise Forbidden("无权限访问该资源")
        return user

    return dependency


require_organizer = require_role(Role.ORGANIZER.value, Role.ADMIN.value)
require_admin = require_role(Role.ADMIN.value)
require_student = require_role(Role.STUDENT.value)


def assert_activity_owner(activity: Activity, user: User) -> User:
    if str(user.role) == Role.ADMIN.value or activity.organizer_id == user.id:
        return user
    raise Forbidden("无权限访问该资源")


def get_activity_or_404(db: Session, activity_id: int) -> Activity:
    activity = db.get(Activity, activity_id)
    if activity is None:
        raise NotFound("活动不存在")
    return activity
