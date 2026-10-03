"""FR-2 活动管理：创建校验、状态机、编辑守卫、列表筛选、详情兜底（§2.4、I-2、S10）。"""

from __future__ import annotations

import time

from helpers import activity_payload, create_activity, create_students, make_user, offset, register


def test_create_activity_validation(client):
    """deadline≤now 400；quota=0 400/422；deadline>start 400（§10.1）。"""
    org = make_user(client, "org1", "ORGANIZER")

    past_deadline = client.post(
        "/api/activities",
        json=activity_payload(signup_deadline=offset(seconds=-60)),
        headers=org["headers"],
    )
    assert past_deadline.status_code == 400 and past_deadline.json()["code"] == 40001
    assert "报名截止时间" in past_deadline.json()["message"]

    zero_quota = client.post("/api/activities", json=activity_payload(quota=0), headers=org["headers"])
    assert zero_quota.status_code == 400 and zero_quota.json()["code"] == 40001

    deadline_after_start = client.post(
        "/api/activities",
        json=activity_payload(start_time=offset(days=1), signup_deadline=offset(days=2)),
        headers=org["headers"],
    )
    assert deadline_after_start.status_code == 400
    assert "报名截止时间不能晚于活动开始时间" in deadline_after_start.json()["message"]

    missing_title = client.post(
        "/api/activities",
        json={"location": "A", "start_time": offset(days=2), "signup_deadline": offset(days=1), "quota": 5},
        headers=org["headers"],
    )
    assert missing_title.status_code == 400


def test_create_defaults_to_draft_and_publish_flow(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = client.post("/api/activities", json=activity_payload(status="DRAFT"), headers=org["headers"]).json()["data"]
    assert activity["status"] == "DRAFT"

    published = client.post(f"/api/activities/{activity['id']}/publish", headers=org["headers"])
    assert published.status_code == 200
    assert published.json()["data"]["status"] == "PUBLISHED"

    again = client.post(f"/api/activities/{activity['id']}/publish", headers=org["headers"])
    assert again.status_code == 400 and "仅草稿" in again.json()["message"]

    cancelled = client.post(f"/api/activities/{activity['id']}/cancel", headers=org["headers"])
    assert cancelled.json()["data"]["status"] == "CANCELLED"
    assert client.post(f"/api/activities/{activity['id']}/cancel", headers=org["headers"]).status_code == 400


def test_edit_guard_blocks_after_lottery(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=10)
    stu = make_user(client, "stu001")
    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=stu["headers"])

    edited = client.patch(
        f"/api/activities/{activity['id']}",
        json={"title": "改名后的活动", "location": "新地点", "quota": 3},
        headers=org["headers"],
    )
    assert edited.status_code == 200
    assert edited.json()["data"]["title"] == "改名后的活动"
    assert edited.json()["data"]["quota"] == 3

    # 提前截止 → 访问详情触发兜底抽签 → 进入 LOTTERY_DONE，此后不可编辑
    closing = client.patch(
        f"/api/activities/{activity['id']}",
        json={"signup_deadline": offset(seconds=-1)},
        headers=org["headers"],
    )
    assert closing.status_code == 200
    detail = client.get(f"/api/activities/{activity['id']}", headers=org["headers"]).json()["data"]
    assert detail["status"] == "LOTTERY_DONE"

    after_lottery = client.patch(f"/api/activities/{activity['id']}", json={"quota": 1}, headers=org["headers"])
    assert after_lottery.status_code == 400 and "不可编辑" in after_lottery.json()["message"]

    cancelled_activity = create_activity(client, org["headers"])
    client.post(f"/api/activities/{cancelled_activity['id']}/cancel", headers=org["headers"])
    assert client.patch(
        f"/api/activities/{cancelled_activity['id']}", json={"quota": 2}, headers=org["headers"]
    ).status_code == 400


def test_edit_rejected_after_real_deadline_passed(client):
    """已截止的活动不可编辑（§7.2 状态边界）。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], signup_deadline=offset(seconds=1))
    time.sleep(1.6)
    response = client.patch(f"/api/activities/{activity['id']}", json={"quota": 2}, headers=org["headers"])
    assert response.status_code == 400
    assert "报名已截止" in response.json()["message"]


def test_quota_shrink_below_won_rejected(client, db):
    """S10 防御性校验：新名额 ≥ 当前 WON 人数。"""
    from datetime import timedelta

    from app.database import utcnow
    from app.models import Activity, ActivityStatus

    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=2)
    students = create_students(client, 3)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    client.patch(
        f"/api/activities/{activity['id']}", json={"signup_deadline": offset(seconds=-1)}, headers=org["headers"]
    )
    client.get(f"/api/activities/{activity['id']}", headers=org["headers"])

    # 把状态复位为「未截止的报名中」，构造出「已有 WON 却仍可编辑」的极端场景
    row = db.get(Activity, activity["id"])
    row.status = ActivityStatus.PUBLISHED
    row.signup_deadline = utcnow() + timedelta(days=1)
    db.commit()

    shrink = client.patch(f"/api/activities/{activity['id']}", json={"quota": 1}, headers=org["headers"])
    assert shrink.status_code == 400
    assert "名额不能少于当前中签人数" in shrink.json()["message"]

    keep = client.patch(f"/api/activities/{activity['id']}", json={"quota": 2}, headers=org["headers"])
    assert keep.status_code == 200


def test_published_activity_can_close_signup_early(client):
    """§2.4 补充约定：PUBLISHED 状态下把截止时间改为过去是允许的，下一次访问触发抽签。"""
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], signup_deadline=offset(days=1))
    moved = client.patch(
        f"/api/activities/{activity['id']}", json={"signup_deadline": offset(seconds=-10)}, headers=org["headers"]
    )
    assert moved.status_code == 200
    detail = client.get(f"/api/activities/{activity['id']}", headers=org["headers"]).json()["data"]
    assert detail["status"] == "LOTTERY_DONE"


def test_detail_contains_my_registration_and_count(client):
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"])
    stu = make_user(client, "stu001")

    detail = client.get(f"/api/activities/{activity['id']}", headers=stu["headers"]).json()["data"]
    assert detail["my_registration"] is None
    assert detail["registered_count"] == 0

    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=stu["headers"])
    detail = client.get(f"/api/activities/{activity['id']}", headers=stu["headers"]).json()["data"]
    assert detail["my_registration"]["status"] == "PENDING"
    assert detail["my_registration"]["qr_available"] is False
    assert detail["registered_count"] == 1
    assert detail["lottery_status_cn"] == "报名中"
    assert detail["signup_deadline"].endswith("Z")

    other = make_user(client, "stu002")
    other_detail = client.get(f"/api/activities/{activity['id']}", headers=other["headers"]).json()["data"]
    assert other_detail["my_registration"] is None


def test_draft_invisible_to_students(client):
    org = make_user(client, "org1", "ORGANIZER")
    draft = client.post("/api/activities", json=activity_payload(status="DRAFT"), headers=org["headers"]).json()["data"]
    stu = make_user(client, "stu001")

    listed = client.get("/api/activities", headers=stu["headers"]).json()["data"]
    assert all(item["id"] != draft["id"] for item in listed["items"])
    assert client.get(f"/api/activities/{draft['id']}", headers=stu["headers"]).status_code == 403
    assert client.get(f"/api/activities/{draft['id']}", headers=org["headers"]).status_code == 200

    forbidden_filter = client.get("/api/activities", params={"status": "DRAFT"}, headers=stu["headers"])
    assert forbidden_filter.status_code == 400


def test_list_mine_and_keyword_filters(client):
    org1 = make_user(client, "org1", "ORGANIZER")
    org2 = make_user(client, "org2", "ORGANIZER")
    create_activity(client, org1["headers"], title="马拉松")
    create_activity(client, org2["headers"], title="摄影")

    mine = client.get("/api/activities", params={"mine": "true"}, headers=org1["headers"]).json()["data"]
    assert mine["total"] == 1
    assert mine["items"][0]["title"] == "马拉松"

    keyword = client.get("/api/activities", params={"keyword": "摄影"}, headers=org1["headers"]).json()["data"]
    assert keyword["total"] == 1

    student = make_user(client, "stu001")
    assert client.get("/api/activities", params={"mine": "true"}, headers=student["headers"]).status_code == 403


def test_not_found_activity(client):
    org = make_user(client, "org1", "ORGANIZER")
    missing = client.get("/api/activities/9999", headers=org["headers"])
    assert missing.status_code == 404 and missing.json()["code"] == 40401
