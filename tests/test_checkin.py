"""FR-6 签到：校验链、重复签到、跨活动码、伪码、手动补签。"""

from __future__ import annotations

from sqlalchemy import func, select

from app.config import get_settings
from app.models import Registration
from app.models import User
from helpers import create_activity, create_students, make_user, run_lottery


def _winner_registrations(client, db, org, activity_id):
    """返回 [(student_headers, username, registration_id, qr_token)]，按 lottery_rank 升序。"""
    rows = client.get(
        f"/api/activities/{activity_id}/winners", headers=org["headers"]
    ).json()["data"]["winners"]
    db.expire_all()
    students = client.get(
        f"/api/activities/{activity_id}/registrations", params={"size": 50}, headers=org["headers"]
    ).json()["data"]["items"]
    by_username = {row["username"]: row for row in students}

    result = []
    for row in rows:
        username = row["user"]["username"]
        registration = db.scalar(
            select(Registration).where(
                Registration.activity_id == activity_id, Registration.user_id == row["user"]["id"]
            )
        )
        result.append(
            {
                "username": username,
                "registration_id": registration.id,
                "qr_token": registration.qr_token,
                "checked_in_at": by_username[username]["checked_in_at"],
            }
        )
    return result


def _setup(client, db, quota: int = 2, students_count: int = 5):
    org = make_user(client, "org1", "ORGANIZER")
    other_org = make_user(client, "org2", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=quota)
    second_activity = create_activity(client, other_org["headers"], quota=quota, title="第二场活动")
    students = create_students(client, students_count)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
        client.post(f"/api/activities/{second_activity['id']}/registrations", json={}, headers=student["headers"])
    run_lottery(client, org["headers"], activity["id"])
    run_lottery(client, other_org["headers"], second_activity["id"])
    return org, other_org, activity, second_activity, students


def test_checkin_success_by_code(client, db):
    org, _other, activity, _second, _students = _setup(client, db)
    winners = _winner_registrations(client, db, org, activity["id"])
    target = winners[0]

    response = client.post(
        f"/api/activities/{activity['id']}/checkin",
        json={"code": target["qr_token"]},
        headers=org["headers"],
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["username"] == target["username"]
    assert data["user_name"]
    assert data["checked_in_at"].endswith("Z")

    listed = client.get(f"/api/activities/{activity['id']}/checkins", headers=org["headers"]).json()["data"]
    assert len(listed["checked_in"]) == 1
    assert listed["checked_in"][0]["user"]["username"] == target["username"]
    assert len(listed["not_checked_in"]) == 1
    assert listed["not_checked_in"][0]["checked_in_at"] is None


def test_checkin_accepts_full_qrcode_url(client, db):
    org, _other, activity, _second, _students = _setup(client, db)
    target = _winner_registrations(client, db, org, activity["id"])[0]
    url = f"{get_settings().PUBLIC_BASE_URL}/checkin.html?code={target['qr_token']}"

    response = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": url}, headers=org["headers"]
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == target["username"]


def test_checkin_duplicate_returns_first_time(client, db):
    org, _other, activity, _second, _students = _setup(client, db)
    target = _winner_registrations(client, db, org, activity["id"])[0]

    client.post(f"/api/activities/{activity['id']}/checkin", json={"code": target["qr_token"]}, headers=org["headers"])
    second = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": target["qr_token"]}, headers=org["headers"]
    )
    assert second.status_code == 409
    body = second.json()
    assert body["code"] == 40901
    assert "该同学已于" in body["message"] and "签到" in body["message"]
    assert body["data"]["checked_in_at"] is not None

    # 提示里的 HH:mm 必须是本地时区，不能把 UTC 墙上时间当成当地时间展示（R3）
    from datetime import datetime

    first_at = datetime.fromisoformat(body["data"]["checked_in_at"].replace("Z", "+00:00"))
    assert f"已于 {first_at.astimezone():%H:%M} 签到" in body["message"]

    # 数据库层只有一条签到记录
    from app.models import Checkin

    db.expire_all()
    assert db.scalar(select(func.count(Checkin.id))) == 1


def test_checkin_cross_activity_code_rejected(client, db):
    """A 活动的码拿到 B 活动签到 → 40001。"""
    org, other_org, activity, second_activity, _students = _setup(client, db)
    target = _winner_registrations(client, db, other_org, second_activity["id"])[0]

    response = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": target["qr_token"]}, headers=org["headers"]
    )
    assert response.status_code == 400 and response.json()["code"] == 40001
    assert "不属于本活动" in response.json()["message"]


def test_checkin_invalid_and_empty_code(client, db):
    org, _other, activity, _second, _students = _setup(client, db)

    invalid = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": "not-a-real-token"}, headers=org["headers"]
    )
    assert invalid.status_code == 404 and invalid.json()["code"] == 40401

    empty = client.post(f"/api/activities/{activity['id']}/checkin", json={"code": "  "}, headers=org["headers"])
    assert empty.status_code == 400 and empty.json()["message"] == "签到码不能为空"


def test_checkin_waitlist_student_rejected(client, db):
    """候补者无码可签：伪造其 registration 的码 → 状态非 WON 40001。"""
    from app.models import RegistrationStatus

    org, _other, activity, _second, students = _setup(client, db)
    rows = client.get(
        f"/api/activities/{activity['id']}/registrations", params={"status": "WAITING", "size": 50}, headers=org["headers"]
    ).json()["data"]["items"]
    waiting = rows[0]
    db.expire_all()
    registration = db.get(Registration, waiting["id"])
    registration.qr_token = "manual-set-token-for-test"
    registration.status = RegistrationStatus.WAITING
    db.commit()

    response = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": "manual-set-token-for-test"}, headers=org["headers"]
    )
    assert response.status_code == 400 and "不是中签状态" in response.json()["message"]


def test_manual_checkin_by_username(client, db):
    """FR-6.7：按学号补签，method=MANUAL。"""
    org, _other, activity, _second, _students = _setup(client, db)
    target = _winner_registrations(client, db, org, activity["id"])[0]

    response = client.post(
        f"/api/activities/{activity['id']}/checkin/manual",
        json={"username": target["username"]},
        headers=org["headers"],
    )
    assert response.status_code == 200
    assert response.json()["data"]["method"] == "MANUAL"

    listed = client.get(f"/api/activities/{activity['id']}/checkins", headers=org["headers"]).json()["data"]
    assert listed["checked_in"][0]["method"] == "MANUAL"

    # 未报名该活动的学生补签 → 40001
    stranger = make_user(client, "stu099")
    missing = client.post(
        f"/api/activities/{activity['id']}/checkin/manual", json={"username": "stu099"}, headers=org["headers"]
    )
    assert missing.status_code == 400
    assert "未报名" in missing.json()["message"]

    # 已签到者再补签 → 40901
    repeated = client.post(
        f"/api/activities/{activity['id']}/checkin/manual",
        json={"username": target["username"]},
        headers=org["headers"],
    )
    assert repeated.status_code == 409


def test_checkin_rejected_for_cancelled_activity(client, db):
    org, _other, activity, _second, _students = _setup(client, db)
    target = _winner_registrations(client, db, org, activity["id"])[0]

    client.post(f"/api/activities/{activity['id']}/cancel", headers=org["headers"])
    response = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": target["qr_token"]}, headers=org["headers"]
    )
    assert response.status_code == 400 and "已取消" in response.json()["message"]


def test_checkin_rejected_before_lottery(client, db):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    (student,) = create_students(client, 1)
    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    response = client.post(
        f"/api/activities/{activity['id']}/checkin", json={"code": "whatever"}, headers=org["headers"]
    )
    assert response.status_code == 400 and "尚未抽签" in response.json()["message"]
