"""测试公共辅助函数。"""

from __future__ import annotations

import time
from datetime import timedelta

from app.database import utcnow

DEFAULT_PASSWORD = "123456"


def iso(dt) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def offset(seconds: int = 0, days: int = 0) -> str:
    return iso(utcnow() + timedelta(days=days, seconds=seconds))


def register(client, username: str, role: str = "STUDENT", real_name: str | None = None, password: str = DEFAULT_PASSWORD):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "password": password,
            "real_name": real_name or f"用户-{username}",
            "role": role,
        },
    )


def login(client, username: str, password: str = DEFAULT_PASSWORD) -> str:
    body = client.post("/api/auth/login", json={"username": username, "password": password}).json()
    return body["data"]["access_token"]


def make_user(client, username: str, role: str = "STUDENT") -> dict:
    register(client, username, role)
    token = login(client, username)
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}, "username": username}


def activity_payload(**overrides) -> dict:
    payload = {
        "title": "AI 前沿讲座",
        "description": "特邀教授主讲",
        "location": "图书馆报告厅",
        "start_time": offset(days=3),
        "end_time": offset(days=3, seconds=7200),
        "signup_deadline": offset(days=1),
        "quota": 10,
        "status": "PUBLISHED",
    }
    payload.update(overrides)
    return payload


def create_activity(client, headers: dict, **overrides) -> dict:
    response = client.post("/api/activities", json=activity_payload(**overrides), headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def create_students(client, count: int, prefix: str = "stu") -> list[dict]:
    return [make_user(client, f"{prefix}{index:03d}") for index in range(1, count + 1)]


def signup_many(client, activity_id: int, users: list[dict], accept_waitlist: bool = True) -> None:
    for user in users:
        response = client.post(
            f"/api/activities/{activity_id}/registrations",
            json={"accept_waitlist": accept_waitlist},
            headers=user["headers"],
        )
        assert response.status_code == 200, response.text


def wait_until_deadline(seconds: float = 1.2) -> None:
    time.sleep(seconds)


def close_signup(client, headers: dict, activity_id: int) -> None:
    """组织者提前截止报名（把 deadline 置为过去）。"""
    response = client.patch(
        f"/api/activities/{activity_id}", json={"signup_deadline": offset(seconds=-5)}, headers=headers
    )
    assert response.status_code == 200, response.text


def run_lottery(client, headers: dict, activity_id: int) -> dict:
    close_signup(client, headers, activity_id)
    response = client.post(f"/api/activities/{activity_id}/lottery", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


def user_id(db, username: str) -> int:
    """按用户名取 id，供直插数据库的测试使用。"""
    from sqlalchemy import select

    from app.models import User

    return db.scalar(select(User.id).where(User.username == username))


def create_admin(db, username: str = "admin", password: str = DEFAULT_PASSWORD) -> int:
    """ADMIN 不能通过注册接口创建（FR-1.2），测试用直插方式准备管理员账号。"""
    from sqlalchemy import select

    from app.models import Role, User
    from app.security import hash_password

    user = db.scalar(select(User).where(User.username == username))
    if user is None:
        user = User(
            username=username,
            password_hash=hash_password(password),
            real_name="系统管理员",
            role=Role.ADMIN.value,
            is_active=1,
        )
        db.add(user)
        db.commit()
    return user.id


def admin_session(client, db) -> dict:
    create_admin(db)
    token = login(client, "admin")
    return {"token": token, "headers": {"Authorization": f"Bearer {token}"}, "username": "admin"}
