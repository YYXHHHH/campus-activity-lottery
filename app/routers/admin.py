"""M9 管理员用户管理（§2.11、§3.6）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import build_page, clamp_page, get_db, utcnow
from app.deps import require_admin
from app.errors import BadRequest, NotFound, ok
from app.models import Role, User
from app.schemas import AdminUserPatch, UserOut

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def list_users(
    keyword: str | None = Query(default=None),
    role: str | None = Query(default=None),
    page: int = Query(default=1),
    size: int = Query(default=10),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    page, size = clamp_page(page, size)
    filters = []
    if role:
        if role not in {item.value for item in Role}:
            raise BadRequest("角色取值不合法")
        filters.append(User.role == role)
    if keyword:
        like = f"%{keyword[:50]}%"
        filters.append(or_(User.username.like(like), User.real_name.like(like)))

    total = db.scalar(select(func.count(User.id)).where(*filters)) or 0
    rows = db.scalars(
        select(User).where(*filters).order_by(User.id.asc()).offset((page - 1) * size).limit(size)
    ).all()
    items = [UserOut.model_validate(row).model_dump(mode="json") for row in rows]
    return ok(build_page(items, total, page, size))


@router.patch("/users/{user_id}")
def patch_user(
    user_id: int,
    payload: AdminUserPatch,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("用户不存在")

    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise BadRequest("没有需要修改的字段")

    if "role" in changes:
        if str(user.role) == Role.ADMIN.value:
            raise BadRequest("不能修改管理员账号的角色")
        changes["role"] = str(changes["role"])

    for field, value in changes.items():
        setattr(user, field, value)
    user.updated_at = utcnow()
    db.commit()
    logger.info("[admin] 修改用户 user_id=%s changes=%s operator=%s", user_id, changes, admin.id)
    return ok(UserOut.model_validate(user).model_dump(mode="json"))
