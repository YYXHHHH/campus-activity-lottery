"""M0 ORM 模型（§4.2 DDL 映射、§4.4 实现要点）。"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, utcnow


class _StrEnum(str, enum.Enum):
    """令 `str(member)` 返回取值本身（"DRAFT"），避免枚举 repr 混入业务字符串。"""

    def __str__(self) -> str:
        return self.value


class ActivityStatus(_StrEnum):
    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    LOTTERY_DONE = "LOTTERY_DONE"
    CANCELLED = "CANCELLED"


class RegistrationStatus(_StrEnum):
    PENDING = "PENDING"
    WON = "WON"
    WAITING = "WAITING"
    LOST = "LOST"
    CANCELLED = "CANCELLED"
    WITHDRAWN = "WITHDRAWN"


class CheckinMethod(_StrEnum):
    SCAN = "SCAN"
    MANUAL = "MANUAL"


class Role(_StrEnum):
    STUDENT = "STUDENT"
    ORGANIZER = "ORGANIZER"
    ADMIN = "ADMIN"


def _enum(column_type):
    return SAEnum(column_type, native_enum=False, length=20, values_callable=lambda e: [m.value for m in e])


ACTIVITY_STATUS_CN = {
    "DRAFT": "草稿",
    "PUBLISHED": "报名中",
    "LOTTERY_DONE": "已抽签",
    "CANCELLED": "已取消",
}
REGISTRATION_STATUS_CN = {
    "PENDING": "待抽签",
    "WON": "已中签",
    "WAITING": "候补中",
    "LOST": "未中签",
    "CANCELLED": "已取消",
    "WITHDRAWN": "已退出",
}
ROLE_CN = {"STUDENT": "学生", "ORGANIZER": "组织者", "ADMIN": "管理员"}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    real_name: Mapped[str] = mapped_column(String(50), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=Role.STUDENT.value)
    email: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    __table_args__ = (Index("ix_users_role", "role"),)


class Activity(Base):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organizer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str] = mapped_column(String(200), nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    signup_deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    quota: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ActivityStatus] = mapped_column(_enum(ActivityStatus), nullable=False, default=ActivityStatus.DRAFT)
    lottery_seed: Mapped[str | None] = mapped_column(String(64))
    lottery_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    registrations: Mapped[list["Registration"]] = relationship(
        back_populates="activity", cascade="all, delete-orphan", passive_deletes=True
    )
    organizer: Mapped["User"] = relationship(foreign_keys=[organizer_id])

    __table_args__ = (
        CheckConstraint("quota >= 1"),
        Index("ix_act_status_deadline", "status", "signup_deadline"),
        Index("ix_act_organizer", "organizer_id"),
    )


class Registration(Base):
    __tablename__ = "registrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[RegistrationStatus] = mapped_column(
        _enum(RegistrationStatus), nullable=False, default=RegistrationStatus.PENDING
    )
    accept_waitlist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    lottery_rank: Mapped[int | None] = mapped_column(Integer)
    qr_token: Mapped[str | None] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    activity: Mapped["Activity"] = relationship(back_populates="registrations")
    user: Mapped["User"] = relationship()
    checkin: Mapped["Checkin | None"] = relationship(
        back_populates="registration", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        UniqueConstraint("activity_id", "user_id"),
        Index("ix_reg_act_status", "activity_id", "status"),
        Index("ix_reg_user", "user_id"),
        Index("ix_reg_rank", "activity_id", "status", "lottery_rank"),
    )


class Checkin(Base):
    __tablename__ = "checkins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    registration_id: Mapped[int] = mapped_column(
        ForeignKey("registrations.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    activity_id: Mapped[int] = mapped_column(ForeignKey("activities.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    checkin_code: Mapped[str | None] = mapped_column(String(64))
    method: Mapped[CheckinMethod] = mapped_column(_enum(CheckinMethod), nullable=False, default=CheckinMethod.SCAN)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    registration: Mapped["Registration"] = relationship(back_populates="checkin")
    user: Mapped["User"] = relationship(foreign_keys=[user_id])
    operator: Mapped["User | None"] = relationship(foreign_keys=[operator_id])

    __table_args__ = (
        Index("ix_checkin_act", "activity_id"),
        Index("ix_checkin_user", "user_id"),
    )
