"""FR-4 抽签：结果分布、幂等、随机性、截止守卫。"""

from __future__ import annotations

from helpers import admin_session, close_signup, create_activity, create_students, make_user, run_lottery


def _winners(client, headers, activity_id):
    return client.get(f"/api/activities/{activity_id}/winners", headers=headers).json()["data"]


def _registrations(client, headers, activity_id, status=None):
    params = {"size": 50}
    if status:
        params["status"] = status
    return client.get(
        f"/api/activities/{activity_id}/registrations", params=params, headers=headers
    ).json()["data"]["items"]


def test_lottery_basic_distribution(client):
    """20 人报名 / 10 名额 → 10 WON + 10 WAITING（FR-4.4/4.5）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    students = create_students(client, 20)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={"accept_waitlist": True}, headers=student["headers"])

    result = run_lottery(client, org["headers"], activity["id"])
    assert result["executed"] is True
    assert (result["won"], result["waiting"], result["lost"]) == (10, 10, 0)

    rows = _registrations(client, org["headers"], activity["id"])
    ranks = sorted(row["lottery_rank"] for row in rows)
    assert ranks == list(range(1, 21))  # 同活动内唯一且不重复
    assert len({row["lottery_rank"] for row in rows}) == 20

    winners = _winners(client, org["headers"], activity["id"])
    assert len(winners["winners"]) == 10
    assert len(winners["waitlist"]) == 10
    assert [row["lottery_rank"] for row in winners["winners"]] == list(range(1, 11))
    assert [row["lottery_rank"] for row in winners["waitlist"]] == list(range(11, 21))
    assert all(row["checked_in"] is False for row in winners["winners"])


def test_accept_waitlist_false_becomes_lost(client):
    """不接受候补 → LOST，不进队列（FR-4.5）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    students = create_students(client, 20)

    for index, student in enumerate(students):
        accept = index < 15
        client.post(
            f"/api/activities/{activity['id']}/registrations",
            json={"accept_waitlist": accept},
            headers=student["headers"],
        )

    result = run_lottery(client, org["headers"], activity["id"])
    assert result["won"] == 10
    assert result["waiting"] + result["lost"] == 10
    lost = _registrations(client, org["headers"], activity["id"], status="LOST")
    waiting = _registrations(client, org["headers"], activity["id"], status="WAITING")
    assert len(lost) == result["lost"]
    assert len(waiting) == result["waiting"]
    assert len(lost) + len(waiting) == 10


def test_lottery_all_win_when_registrations_below_quota(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    students = create_students(client, 5)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    result = run_lottery(client, org["headers"], activity["id"])
    assert (result["won"], result["waiting"], result["lost"]) == (5, 0, 0)
    for row in _registrations(client, org["headers"], activity["id"]):
        assert row["status"] == "WON"
        assert row["lottery_rank"] is not None  # rank 仍赋值，便于审计排序


def test_lottery_with_zero_registrations(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=3)
    result = run_lottery(client, org["headers"], activity["id"])
    assert result["executed"] is True
    assert result["won"] == 0
    detail = client.get(f"/api/activities/{activity['id']}", headers=org["headers"]).json()["data"]
    assert detail["status"] == "LOTTERY_DONE"


def test_lottery_idempotent(client):
    """二次调用 executed=False，名单与 rank 不变（FR-4.3）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=5)
    for student in create_students(client, 12):
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    run_lottery(client, org["headers"], activity["id"])
    before = {row["username"]: row["lottery_rank"] for row in _registrations(client, org["headers"], activity["id"])}

    second = client.post(f"/api/activities/{activity['id']}/lottery", headers=org["headers"])
    assert second.status_code == 200
    body = second.json()["data"]
    assert body["executed"] is False
    assert body["reason"] == "already_done"

    after = {row["username"]: row["lottery_rank"] for row in _registrations(client, org["headers"], activity["id"])}
    assert before == after


def test_lottery_before_deadline_rejected(client):
    """FR-4.9：未截止 400；ADMIN force=true 例外。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    for student in create_students(client, 4):
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    early = client.post(f"/api/activities/{activity['id']}/lottery", headers=org["headers"])
    assert early.status_code == 400 and early.json()["code"] == 40001
    assert "尚未截止" in early.json()["message"]

    # 组织者即使显式传 force 也不生效（force 仅 ADMIN 有效）
    forced_by_org = client.post(f"/api/activities/{activity['id']}/lottery", params={"force": "true"}, headers=org["headers"])
    assert forced_by_org.status_code == 400


def test_lottery_force_allowed_for_admin(client, db):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    for student in create_students(client, 4):
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    admin = admin_session(client, db)
    forced = client.post(
        f"/api/activities/{activity['id']}/lottery", params={"force": "true"}, headers=admin["headers"]
    )
    assert forced.status_code == 200
    assert forced.json()["data"]["executed"] is True
    assert forced.json()["data"]["won"] == 2


def test_lottery_randomness_across_activities(client):
    """多轮抽签中签集合不同（FR-4.6）。"""
    org = make_user(client, "org1", "ORGANIZER")
    students = create_students(client, 20)
    sets_ = []
    for index in range(1, 4):
        activity = create_activity(client, org["headers"], quota=10, title=f"随机测试{index}")
        for student in students:
            client.post(
                f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"]
            )
        run_lottery(client, org["headers"], activity["id"])
        sets_.append(frozenset(row["user"]["username"] for row in _winners(client, org["headers"], activity["id"])["winners"]))

    assert len(set(sets_)) > 1


def test_lottery_won_student_gets_qr_available(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=1)
    (student,) = create_students(client, 1)
    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    run_lottery(client, org["headers"], activity["id"])

    mine = client.get("/api/me/registrations", headers=student["headers"]).json()["data"]["items"][0]
    assert mine["status"] == "WON"
    assert mine["qr_available"] is True

    image = client.get(f"/api/registrations/{mine['id']}/qrcode", headers=student["headers"])
    assert image.status_code == 200
    assert image.headers["content-type"] == "image/png"
    assert image.headers["cache-control"] == "no-store"
    assert image.content[:8] == b"\x89PNG\r\n\x1a\n"
