"""FR-5 候补递补。"""

from __future__ import annotations

from datetime import timedelta

from app.database import utcnow
from app.models import Activity, ActivityStatus, Registration, RegistrationStatus
from helpers import create_activity, create_students, make_user, offset, run_lottery


def reopen_activity_for_edit(db, activity_id: int) -> None:
    """把已抽签活动复位为「未截止的报名中」，用于构造名额变更场景（仅测试使用）。"""
    db.expire_all()
    activity = db.get(Activity, activity_id)
    activity.status = ActivityStatus.PUBLISHED
    activity.signup_deadline = utcnow() + timedelta(days=1)
    db.commit()


def _signup_all(client, activity_id: int, students) -> None:
    for student in students:
        client.post(
            f"/api/activities/{activity_id}/registrations", json={"accept_waitlist": True}, headers=student["headers"]
        )


def _status_map(client, headers, activity_id: int) -> dict:
    items = client.get(
        f"/api/activities/{activity_id}/registrations", params={"size": 50}, headers=headers
    ).json()["data"]["items"]
    return {row["username"]: row for row in items}


def test_waitlist_promotion_on_withdraw(client, db):
    """退出后 rank 最小的候补变 WON、获得新签到码、旧码失效、my 接口可见（FR-5.1~5.4/5.7）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    students = create_students(client, 5)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    rows = _status_map(client, org["headers"], activity["id"])
    winners = sorted((row for row in rows.values() if row["status"] == "WON"), key=lambda r: r["lottery_rank"])
    waiters = sorted((row for row in rows.values() if row["status"] == "WAITING"), key=lambda r: r["lottery_rank"])
    assert len(winners) == 2 and len(waiters) == 3

    leaver = next(s for s in students if s["username"] == winners[0]["username"])
    expected_promoted = waiters[0]["username"]

    response = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=leaver["headers"])
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["status"] == "WITHDRAWN"
    assert body["promoted"] == 1

    after = _status_map(client, org["headers"], activity["id"])
    assert after[expected_promoted]["status"] == "WON"
    assert after[leaver["username"]]["status"] == "WITHDRAWN"
    assert after[leaver["username"]]["lottery_rank"] == winners[0]["lottery_rank"]

    # 我的报名：退出者显示已退出，递补者拿到可用签到码
    leaver_mine = client.get("/api/me/registrations", headers=leaver["headers"]).json()["data"]
    assert leaver_mine["items"][0]["status"] == "WITHDRAWN"
    assert leaver_mine["items"][0]["qr_available"] is False

    promoted_user = next(s for s in students if s["username"] == expected_promoted)
    promoted_mine = client.get("/api/me/registrations", headers=promoted_user["headers"]).json()["data"]["items"][0]
    assert promoted_mine["status"] == "WON"
    assert promoted_mine["qr_available"] is True

    # 旧签到码失效：退出者的 qr_token 置空
    from sqlalchemy import select

    from app.models import User

    db.expire_all()
    leaver_user_id = db.scalar(select(User.id).where(User.username == leaver["username"]))
    leaver_registration = db.scalar(
        select(Registration).where(
            Registration.activity_id == activity["id"], Registration.user_id == leaver_user_id
        )
    )
    assert leaver_registration.qr_token is None
    assert str(leaver_registration.status) == "WITHDRAWN"


def test_old_qrcode_rejected_after_withdraw(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=1)
    students = create_students(client, 3)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    rows = _status_map(client, org["headers"], activity["id"])
    winner_row = next(row for row in rows.values() if row["status"] == "WON")
    winner = next(s for s in students if s["username"] == winner_row["username"])

    before = client.get(f"/api/registrations/{winner_row['id']}/qrcode", headers=winner["headers"])
    assert before.status_code == 200

    client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=winner["headers"])
    after = client.get(f"/api/registrations/{winner_row['id']}/qrcode", headers=winner["headers"])
    assert after.status_code == 400 and after.json()["code"] == 40001


def test_promotion_with_empty_waitlist(client):
    """FR-5.5：无候补时退出不报错、名额空缺。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    students = create_students(client, 2)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    response = client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=students[0]["headers"])
    assert response.status_code == 200
    assert response.json()["data"]["promoted"] == 0

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert stats["won"] == 1
    assert stats["quota_usage"] == 0.5


def test_quota_increase_promotes_from_waitlist(client, db):
    """FR-5.6 / I-4：quota 10→12 补足 2 人。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    students = create_students(client, 20)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    reopen_activity_for_edit(db, activity["id"])
    expanded = client.patch(f"/api/activities/{activity['id']}", json={"quota": 12}, headers=org["headers"])
    assert expanded.status_code == 200
    assert expanded.json()["data"]["promoted"] == 2

    rows = _status_map(client, org["headers"], activity["id"])
    assert sum(1 for row in rows.values() if row["status"] == "WON") == 12
    assert sum(1 for row in rows.values() if row["status"] == "WAITING") == 8

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=org["headers"]).json()["data"]
    assert stats["won"] == 12
    assert stats["quota_usage"] == 1.0


def test_quota_increase_without_waitlist(client, db):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=5)
    students = create_students(client, 3)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    reopen_activity_for_edit(db, activity["id"])
    expanded = client.patch(f"/api/activities/{activity['id']}", json={"quota": 8}, headers=org["headers"])
    assert expanded.status_code == 200
    assert expanded.json()["data"]["promoted"] == 0
    assert sum(1 for row in _status_map(client, org["headers"], activity["id"]).values() if row["status"] == "WON") == 3


def test_withdrawn_visible_in_my_list(client):
    """退出记录仍在我的报名中可见（状态 WITHDRAWN），便于学生查看结果。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=1)
    students = create_students(client, 2)
    _signup_all(client, activity["id"], students)
    run_lottery(client, org["headers"], activity["id"])

    rows = _status_map(client, org["headers"], activity["id"])
    winner_row = next(row for row in rows.values() if row["status"] == "WON")
    winner = next(s for s in students if s["username"] == winner_row["username"])
    client.delete(f"/api/activities/{activity['id']}/registrations/me", headers=winner["headers"])

    mine = client.get("/api/me/registrations", headers=winner["headers"]).json()["data"]
    assert mine["items"][0]["status"] == "WITHDRAWN"
    assert mine["items"][0]["qr_available"] is False
