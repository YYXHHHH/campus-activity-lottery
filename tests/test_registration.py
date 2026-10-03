"""FR-3 报名 / 取消 / 我的报名（§2.5、§3.4）。"""

from __future__ import annotations

import time

from helpers import create_activity, create_students, make_user, offset


def test_register_activity_flows(client):
    """成功 → 重复 409 → 截止后 400 → 取消后重报复用记录。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"])
    student = make_user(client, "stu001")

    first = client.post(
        f"/api/activities/{activity['id']}/registrations",
        json={"accept_waitlist": True},
        headers=student["headers"],
    )
    assert first.status_code == 200
    body = first.json()["data"]
    assert body["status"] == "PENDING"
    assert body["accept_waitlist"] is True
    registration_id = body["id"]
    created_at = body["created_at"]

    duplicate = client.post(
        f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"]
    )
    assert duplicate.status_code == 409 and duplicate.json()["code"] == 40901

    # 取消后重报：复用原记录，保留 created_at
    cancelled = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=student["headers"])
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    again = client.post(
        f"/api/activities/{activity['id']}/registrations",
        json={"accept_waitlist": False},
        headers=student["headers"],
    )
    assert again.status_code == 200
    reused = again.json()["data"]
    assert reused["id"] == registration_id
    assert reused["status"] == "PENDING"
    assert reused["accept_waitlist"] is False
    assert reused["created_at"] == created_at


def test_register_after_deadline_rejected(client):
    """S4：now == deadline 即不可报名。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], signup_deadline=offset(seconds=1))
    student = make_user(client, "stu001")

    assert client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"]).status_code == 200

    time.sleep(1.6)
    response = client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    assert response.status_code == 400 and response.json()["code"] == 40001
    assert "报名已截止" in response.json()["message"]


def test_register_requires_published_activity(client):
    org = make_user(client, "org1", "ORGANIZER")
    student = make_user(client, "stu001")

    draft = client.post(
        "/api/activities",
        json={
            "title": "草稿活动",
            "location": "教室",
            "start_time": offset(days=2),
            "signup_deadline": offset(days=1),
            "quota": 5,
            "status": "DRAFT",
        },
        headers=org["headers"],
    ).json()["data"]
    blocked = client.post(f"/api/activities/{draft['id']}/registrations", json={}, headers=student["headers"])
    assert blocked.status_code == 400 and "状态不允许" in blocked.json()["message"]

    cancelled_activity = create_activity(client, org["headers"], title="将被取消的活动")
    client.post(f"/api/activities/{cancelled_activity['id']}/cancel", headers=org["headers"])
    after_cancel = client.post(
        f"/api/activities/{cancelled_activity['id']}/registrations", json={}, headers=student["headers"]
    )
    assert after_cancel.status_code == 400 and "已取消" in after_cancel.json()["message"]

    missing = client.post("/api/activities/9999/registrations", json={}, headers=student["headers"])
    assert missing.status_code == 404 and missing.json()["code"] == 40401


def test_cancel_rules_by_status(client):
    """WON 退出 → WITHDRAWN；重复取消 / WAITING 之外的终态 → 40001；无记录 → 40401。"""
    from helpers import run_lottery

    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=1)
    students = create_students(client, 2)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    run_lottery(client, org["headers"], activity["id"])

    rows = client.get(f"/api/activities/{activity['id']}/winners", headers=org["headers"]).json()["data"]
    by_username = {student["username"]: student for student in students}
    winner = by_username[rows["winners"][0]["user"]["username"]]

    withdraw = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=winner["headers"])
    assert withdraw.status_code == 200
    assert withdraw.json()["data"]["status"] == "WITHDRAWN"

    repeated = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=winner["headers"])
    assert repeated.status_code == 400

    other = [student for student in students if student is not winner][0]
    # 原候补者已被 I-3 递补为 WON，因此其「取消」按退出语义走 WITHDRAWN
    waiting_cancel = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=other["headers"])
    assert waiting_cancel.status_code == 200
    assert waiting_cancel.json()["data"]["status"] == "WITHDRAWN"

    stranger = make_user(client, "stu099")
    missing = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=stranger["headers"])
    assert missing.status_code == 404 and missing.json()["code"] == 40401


def test_my_registrations_list(client):
    org = make_user(client, "org1", "ORGANIZER")
    first_activity = create_activity(client, org["headers"], title="活动一")
    second_activity = create_activity(client, org["headers"], title="活动二")
    student = make_user(client, "stu001")

    client.post(f"/api/activities/{first_activity['id']}/registrations", json={}, headers=student["headers"])
    client.post(f"/api/activities/{second_activity['id']}/registrations", json={}, headers=student["headers"])

    listed = client.get("/api/me/registrations", headers=student["headers"]).json()["data"]
    assert listed["total"] == 2
    # created_at desc：后报名的排在前
    assert listed["items"][0]["activity"]["title"] == "活动二"
    assert listed["items"][0]["qr_available"] is False
    assert listed["items"][0]["status"] == "PENDING"
    assert listed["items"][0]["created_at"].endswith("Z")

    # 取消后不显示在列表
    client.delete(f"/api/activities/{first_activity['id']}/registrations/me", headers=student["headers"])
    after = client.get("/api/me/registrations", headers=student["headers"]).json()["data"]
    assert after["total"] == 1
    assert after["items"][0]["activity"]["title"] == "活动二"
