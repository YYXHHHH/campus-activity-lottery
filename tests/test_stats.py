"""FR-7 统计。"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Registration, User
from helpers import create_activity, create_students, make_user, run_lottery


def _tokens_for(client, db, org, activity_id):
    rows = client.get(f"/api/activities/{activity_id}/winners", headers=org["headers"]).json()["data"]["winners"]
    db.expire_all()
    tokens = {}
    for row in rows:
        registration = db.scalar(
            select(Registration).where(
                Registration.activity_id == activity_id, Registration.user_id == row["user"]["id"]
            )
        )
        tokens[row["user"]["username"]] = registration.qr_token
    return tokens


def test_stats_matches_document_example(client, db):
    """20 人报名 / 10 名额 / 15 人接受候补 / 7 人签到 → 校验六项计数与三项比率的取值。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    students = create_students(client, 20)

    for index, student in enumerate(students):
        client.post(
            f"/api/activities/{activity['id']}/registrations",
            json={"accept_waitlist": index < 15},
            headers=student["headers"],
        )
    run_lottery(client, org["headers"], activity["id"])

    tokens = _tokens_for(client, db, org, activity["id"])
    for username, token in list(tokens.items())[:7]:
        response = client.post(
            f"/api/activities/{activity['id']}/checkin", json={"code": token}, headers=org["headers"]
        )
        assert response.status_code == 200, (username, response.text)

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert stats["activity_id"] == activity["id"]
    assert stats["quota"] == 10
    assert stats["registered"] == 20
    assert stats["pending"] == 0
    assert stats["won"] == 10
    # 候补/未中签的划分取决于随机结果：接受候补者落在后 10 名的进入 WAITING，其余为 LOST
    assert stats["waiting"] + stats["lost"] == 10
    assert stats["withdrawn"] == 0
    assert stats["checked_in"] == 7
    assert stats["win_rate"] == 0.5
    assert stats["checkin_rate"] == 0.7
    assert stats["quota_usage"] == 1.0
    assert stats["lottery_at"].endswith("Z")


def test_stats_zero_denominator_rules(client):
    """分母为 0 时比率取 0（S8）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=5)

    before = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert before["registered"] == 0
    assert before["win_rate"] == 0
    assert before["checkin_rate"] == 0
    assert before["quota_usage"] == 0
    assert before["lottery_at"] is None


def test_stats_ratio_keeps_four_decimals(client, db):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=3)
    for student in create_students(client, 7):
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    run_lottery(client, org["headers"], activity["id"])

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert stats["win_rate"] == round(3 / 7, 4) == 0.4286
    assert stats["checkin_rate"] == 0
    assert stats["quota_usage"] == 1.0


def test_stats_counts_withdrawn_and_cancelled(client, db):
    """registered 含 WITHDRAWN，CANCELLED 不计入。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    students = create_students(client, 4)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    # 取消一人（PENDING → CANCELLED）
    client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=students[0]["headers"])
    run_lottery(client, org["headers"], activity["id"])

    tokens = _tokens_for(client, db, org, activity["id"])
    leaver = next(s for s in students[1:] if s["username"] in tokens)
    client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=leaver["headers"])

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert stats["withdrawn"] == 1
    assert stats["registered"] == 3  # 4 条报名记录中，已取消的那条不计入
    assert stats["cancelled"] == 1
    assert stats["pending"] == 0
    assert stats["won"] == 2
