"""M0 数据库会话、时间工具与 SQLite 并发优化。"""

from __future__ import annotations

import functools
import logging
import time
from datetime import datetime, timezone

from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings

logger = logging.getLogger(__name__)


def utcnow() -> datetime:
    """全项目唯一时间来源（UTC aware）。"""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """把库中读出的 naive UTC 时间统一为 aware，比较前必须调用。"""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso_z(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


class Base(DeclarativeBase):
    pass


settings = get_settings()
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=(
        {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
    ),
    pool_pre_ping=True,
    future=True,
)

if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    from app import models  # noqa: F401  确保模型注册

    Base.metadata.create_all(bind=engine)


def clamp_page(page: int | None, size: int | None) -> tuple[int, int]:
    """分页入参归一：page ≥ 1，size 默认 10、上限 50。"""
    return max(1, int(page or 1)), min(50, max(1, int(size or 10)))


def build_page(items: list, total: int, page: int, size: int) -> dict:
    """统一分页响应结构（S2）。"""
    pages = (total + size - 1) // size if size else 0
    return {"items": items, "total": total, "page": page, "size": size, "pages": pages}


def retry_on_locked(times: int = 3, base_delay: float = 0.05):
    """SQLite `database is locked` 退避重试，用于高频写用例函数。"""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            db = kwargs.get("db") or next((arg for arg in args if isinstance(arg, Session)), None)
            delay = base_delay
            for attempt in range(times + 1):
                try:
                    return func(*args, **kwargs)
                except OperationalError as exc:
                    if "database is locked" not in str(exc).lower() or attempt >= times:
                        raise
                    logger.warning("[db] database is locked，%sms 后重试（第 %s 次）", int(delay * 1000), attempt + 1)
                    if db is not None:
                        db.rollback()
                    time.sleep(delay)
                    delay *= 2

        return wrapper

    return decorator
