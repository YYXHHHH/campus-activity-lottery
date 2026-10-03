"""M0 Pydantic 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.database import iso_z

UtcDatetime = Annotated[datetime, PlainSerializer(iso_z, return_type=str, when_used="json")]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class PageOut(BaseModel):
    items: list[Any]
    total: int
    page: int
    size: int
    pages: int


# ---------- 认证 ----------
class RegisterIn(BaseModel):
    username: str = Field(min_length=4, max_length=50, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=6, max_length=64)
    real_name: str = Field(min_length=1, max_length=50)
    role: Literal["STUDENT", "ORGANIZER"]
    email: str | None = None
    phone: str | None = None


class LoginIn(BaseModel):
    username: str
    password: str


class UserOut(ORMModel):
    id: int
    username: str
    real_name: str
    role: str
    email: str | None
    phone: str | None
    is_active: int
    created_at: UtcDatetime


class AdminUserOut(UserOut):
    pass


# ---------- 活动 ----------
class ActivityCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str | None = None
    location: str = Field(min_length=1, max_length=200)
    start_time: datetime
    end_time: datetime | None = None
    signup_deadline: datetime
    quota: int = Field(ge=1, le=100000)
    status: Literal["DRAFT", "PUBLISHED"] = "DRAFT"


class ActivityUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    location: str | None = Field(default=None, min_length=1, max_length=200)
    start_time: datetime | None = None
    end_time: datetime | None = None
    signup_deadline: datetime | None = None
    quota: int | None = Field(default=None, ge=1, le=100000)


class ActivityOut(ORMModel):
    id: int
    organizer_id: int
    title: str
    description: str | None
    location: str
    start_time: UtcDatetime
    end_time: UtcDatetime | None
    signup_deadline: UtcDatetime
    quota: int
    status: str
    lottery_at: UtcDatetime | None
    created_at: UtcDatetime


class MyRegistrationBrief(BaseModel):
    id: int
    status: str
    lottery_rank: int | None
    qr_available: bool
    accept_waitlist: bool
    checked_in: bool


class ActivityDetailOut(ActivityOut):
    my_registration: MyRegistrationBrief | None = None
    registered_count: int = 0
    lottery_status_cn: str = ""


# ---------- 报名 ----------
class RegistrationCreate(BaseModel):
    accept_waitlist: bool = True


class AdminUserPatch(BaseModel):
    role: Literal["STUDENT", "ORGANIZER"] | None = None
    is_active: Literal[0, 1] | None = None


class CheckinIn(BaseModel):
    code: str


class ManualCheckinIn(BaseModel):
    username: str


class RegistrationOut(ORMModel):
    id: int
    activity_id: int
    user_id: int
    username: str
    real_name: str
    status: str
    accept_waitlist: bool
    lottery_rank: int | None
    checked_in_at: UtcDatetime | None
    created_at: UtcDatetime


class ActivityBrief(ORMModel):
    id: int
    title: str
    location: str
    start_time: UtcDatetime
    signup_deadline: UtcDatetime
    quota: int
    status: str


class MyRegistrationOut(BaseModel):
    id: int
    status: str
    lottery_rank: int | None
    qr_available: bool
    checked_in: bool
    accept_waitlist: bool
    created_at: UtcDatetime
    activity: ActivityBrief


class RegistrationBrief(BaseModel):
    username: str
    real_name: str


class UserBrief(ORMModel):
    id: int
    username: str
    real_name: str


class CheckinRow(BaseModel):
    user: UserBrief
    checked_in_at: UtcDatetime | None
    method: str | None = None


class WinRow(BaseModel):
    registration_id: int
    user: UserBrief
    lottery_rank: int
    checked_in: bool
