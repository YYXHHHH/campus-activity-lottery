"""M9 管理员用户管理（§2.11、§3.6）。"""

from __future__ import annotations

from helpers import admin_session, create_students, login, make_user, register


def test_admin_only_access(client, db):
    student = make_user(client, "stu001")
    org = make_user(client, "org1", "ORGANIZER")
    assert client.get("/api/admin/users", headers=student["headers"]).status_code == 403
    assert client.get("/api/admin/users", headers=org["headers"]).status_code == 403
    admin = admin_session(client, db)
    assert client.get("/api/admin/users", headers=admin["headers"]).status_code == 200


def test_admin_list_filters_and_pagination(client, db):
    admin = admin_session(client, db)
    create_students(client, 12)
    make_user(client, "org1", "ORGANIZER")
    make_user(client, "org2", "ORGANIZER")

    everyone = client.get("/api/admin/users", params={"size": 50}, headers=admin["headers"]).json()["data"]
    assert everyone["total"] == 15  # admin + 12 学生 + 2 组织者

    by_role = client.get("/api/admin/users", params={"role": "ORGANIZER", "size": 50}, headers=admin["headers"]).json()["data"]
    assert by_role["total"] == 2
    assert {row["username"] for row in by_role["items"]} == {"org1", "org2"}

    by_keyword = client.get("/api/admin/users", params={"keyword": "stu001"}, headers=admin["headers"]).json()["data"]
    assert by_keyword["total"] == 1

    paged = client.get("/api/admin/users", params={"page": 2, "size": 5}, headers=admin["headers"]).json()["data"]
    assert (paged["page"], paged["size"], paged["pages"], len(paged["items"])) == (2, 5, 3, 5)

    bad_role = client.get("/api/admin/users", params={"role": "ROOT"}, headers=admin["headers"])
    assert bad_role.status_code == 400 and bad_role.json()["code"] == 40001


def test_role_change_rules(client, db):
    """仅可在 STUDENT/ORGANIZER 间互改，不能提为 ADMIN，不能改 ADMIN 角色（§2.11）。"""
    admin = admin_session(client, db)
    student = make_user(client, "stu001")
    student_id = client.get("/api/admin/users", params={"keyword": "stu001"}, headers=admin["headers"]).json()["data"]["items"][0]["id"]

    promoted = client.patch(f"/api/admin/users/{student_id}", json={"role": "ORGANIZER"}, headers=admin["headers"])
    assert promoted.status_code == 200
    assert promoted.json()["data"]["role"] == "ORGANIZER"

    # 角色变更后旧 token 的下一次请求即按新角色判定
    me = client.get("/api/auth/me", headers=student["headers"])
    assert me.json()["data"]["role"] == "ORGANIZER"
    assert client.post("/api/activities", json={}, headers=student["headers"]).status_code in (400, 422)

    demoted = client.patch(f"/api/admin/users/{student_id}", json={"role": "STUDENT"}, headers=admin["headers"])
    assert demoted.json()["data"]["role"] == "STUDENT"

    to_admin = client.patch(f"/api/admin/users/{student_id}", json={"role": "ADMIN"}, headers=admin["headers"])
    assert to_admin.status_code == 400 and to_admin.json()["code"] == 40001

    admin_row = client.get("/api/admin/users", params={"keyword": "admin"}, headers=admin["headers"]).json()["data"]["items"][0]
    change_admin = client.patch(f"/api/admin/users/{admin_row['id']}", json={"role": "ORGANIZER"}, headers=admin["headers"])
    assert change_admin.status_code == 400
    assert "不能修改管理员账号的角色" in change_admin.json()["message"]

    missing = client.patch("/api/admin/users/9999", json={"role": "ORGANIZER"}, headers=admin["headers"])
    assert missing.status_code == 404 and missing.json()["code"] == 40401

    empty_body = client.patch(f"/api/admin/users/{student_id}", json={}, headers=admin["headers"])
    assert empty_body.status_code == 400


def test_disable_takes_effect_immediately(client, db):
    admin = admin_session(client, db)
    student = make_user(client, "stu001")
    student_id = client.get("/api/admin/users", params={"keyword": "stu001"}, headers=admin["headers"]).json()["data"]["items"][0]["id"]

    disabled = client.patch(f"/api/admin/users/{student_id}", json={"is_active": 0}, headers=admin["headers"])
    assert disabled.json()["data"]["is_active"] == 0

    assert client.get("/api/auth/me", headers=student["headers"]).status_code == 401
    assert client.post("/api/auth/login", json={"username": "stu001", "password": "123456"}).status_code == 401

    enabled = client.patch(f"/api/admin/users/{student_id}", json={"is_active": 1}, headers=admin["headers"])
    assert enabled.json()["data"]["is_active"] == 1
    assert client.get("/api/auth/me", headers=student["headers"]).status_code == 200
    assert login(client, "stu001")


def test_admin_cannot_be_created_via_register(client, db):
    admin_session(client, db)
    response = register(client, "sneaky01", "ADMIN")
    assert response.status_code == 400 and response.json()["code"] == 40001
