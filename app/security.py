"""M0 密码哈希与 JWT 签发解析。"""

from __future__ import annotations

import logging
import os
from datetime import timedelta

import jwt
from passlib.context import CryptContext

from app.config import get_settings
from app.database import utcnow

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
# 测试环境用 BCRYPT_ROUNDS=4 降低哈希成本以加速批量建用户；生产保持默认 12
_ctx = CryptContext(
    schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=int(os.getenv("BCRYPT_ROUNDS", "12"))
)


def hash_password(password: str) -> str:
    return _ctx.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _ctx.verify(password, password_hash)
    except Exception as exc:  # bcrypt/passlib 版本异常一律视为验证失败
        logger.warning("[security] 密码校验异常：%s", exc)
        return False


def create_access_token(user) -> tuple[str, int]:
    settings = get_settings()
    expires_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    issued_at = utcnow()
    payload = {
        "sub": str(user.id),
        "role": str(user.role),
        "iat": int(issued_at.timestamp()),
        "exp": int((issued_at + timedelta(seconds=expires_seconds)).timestamp()),
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)
    return token, expires_seconds


class TokenError(Exception):
    """token 过期/篡改/结构非法。"""


def decode_token(token: str) -> int:
    """解析 token，返回用户 id。失败抛 TokenError，由 get_current_user 转 40101。"""
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise TokenError(str(exc)) from exc
    try:
        return int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TokenError("invalid payload") from exc
