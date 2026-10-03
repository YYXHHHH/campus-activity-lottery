"""S2/S3 分页与排序约定。"""

from __future__ import annotations

from helpers import create_activity, create_students, make_user, offset, register


def _keys(data):
    return set(data)


def test_pagination_structure_and_clamp(client):
    org = make_user(client, "org1", "ORGANIZER")
    for index in range(3):
        create_activity(client, org["headers"], title=f"活动{index}")

    page = client.get("/api/activities", params={"page": 1, "size": 1}, headers=org["headers"]).json()["data"]
    assert _keys(page) == {"items", "total", "page", "size", "pages"}
    assert page["total"] == 3
    assert page["pages"] == 3
    assert len(page["items"]) == 1

    clamped = client.get("/api/activities", params={"size": 100}, headers=org["headers"]).json()["data"]
    assert clamped["size"] == 50

    negative_page = client.get("/api/activities", params={"page": 0, "size": 0}, headers=org["headers"]).json()["data"]
    assert negative_page["page"] == 1
    assert negative_page["size"] == 10

    empty = client.get("/api/activities", params={"page": 9}, headers=org["headers"]).json()["data"]
    assert empty["items"] == [] and empty["total"] == 3


def test_activities_sorted_by_created_at_desc(client):
    org = make_user(client, "org1", "ORGANIZER")
    titles = [f"排序活动{index}" for index in range(4)]
    for title in titles:
        create_activity(client, org["headers"], title=title)

    items = client.get("/api/activities", params={"size": 50}, headers=org["headers"]).json()["data"]["items"]
    assert [item["title"] for item in items] == list(reversed(titles))
    created = [item["created_at"] for item in items]
    assert created == sorted(created, reverse=True)


def test_winners_and_registrations_ordering(client):
    from helpers import run_lottery

    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=3)
    students = create_students(client, 8)
    for student in students:
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])
    run_lottery(client, org["headers"], activity["id"])

    registrations = client.get(
        f"/api/activities/{activity['id']}/registrations", params={"size": 50}, headers=org["headers"]
    ).json()["data"]["items"]
    assert [row["id"] for row in registrations] == sorted(row["id"] for row in registrations)  # id asc

    winners = client.get(f"/api/activities/{activity['id']}/winners", headers=org["headers"]).json()["data"]
    assert [row["lottery_rank"] for row in winners["winners"]] == [1, 2, 3]
    assert [row["lottery_rank"] for row in winners["waitlist"]] == [4, 5, 6, 7, 8]


def test_checkins_sorted_by_time_asc(client, db):
    from sqlalchemy import select

    from app.models import Registration

    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"], quota=3)
    for student in create_students(client, 6):
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    from helpers import run_lottery

    run_lottery(client, org["headers"], activity["id"])
    rows = client.get(f"/api/activities/{activity['id']}/winners", headers=org["headers"]).json()["data"]["winners"]
    for row in rows:
        db.expire_all()
        token = db.scalar(
            select(Registration.qr_token).where(
                Registration.activity_id == activity["id"], Registration.user_id == row["user"]["id"]
            )
        )
        assert client.post(
            f"/api/activities/{activity['id']}/checkin", json={"code": token}, headers=org["headers"]
        ).status_code == 200

    listed = client.get(f"/api/activities/{activity['id']}/checkins", headers=org["headers"]).json()["data"]
    times = [row["checked_in_at"] for row in listed["checked_in"]]
    assert times == sorted(times)
    assert len(times) == 3
    assert all(row["checked_in_at"] is None for row in listed["not_checked_in"])


def test_keyword_truncated_to_50_chars(client):
    org = make_user(client, "org1", "ORGANIZER")
    create_activity(client, org["headers"], title="关键词测试")
    long_keyword = "A" * 200
    response = client.get("/api/activities", params={"keyword": long_keyword}, headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0


def test_my_registrations_pagination(client):
    org = make_user(client, "org1", "ORGANIZER")
    student = make_user(client, "stu001")
    for index in range(12):
        activity = create_activity(client, org["headers"], title=f"分页活动{index}")
        client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    first = client.get("/api/me/registrations", params={"size": 5}, headers=student["headers"]).json()["data"]
    assert (first["total"], first["pages"], len(first["items"])) == (12, 3, 5)
    second = client.get("/api/me/registrations", params={"size": 5, "page": 2}, headers=student["headers"]).json()["data"]
    assert {row["id"] for row in first["items"]}.isdisjoint({row["id"] for row in second["items"]})
