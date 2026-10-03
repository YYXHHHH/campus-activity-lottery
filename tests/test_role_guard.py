"""FR-2.8 权限边界：角色 + 归属双重校验（§7.2 权限边界）。"""

from __future__ import annotations

from helpers import admin_session, create_activity, create_students, login, make_user, register


def _organizers_and_activity(client):
    org1 = make_user(client, "org1", "ORGANIZER")
    org2 = make_user(client, "org2", "ORGANIZER")
    activity = create_activity(client, org1["headers"])
    return org1, org2, activity


def test_student_cannot_manage_activities(client):
    student = make_user(client, "stu001")
    org = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org["headers"])

    for method, path in [
        ("post", "/api/activities"),
        ("patch", f"/api/activities/{activity['id']}"),
        ("post", f"/api/activities/{activity['id']}/publish"),
        ("post", f"/api/activities/{activity['id']}/cancel"),
        ("post", f"/api/activities/{activity['id']}/lottery"),
        ("get", f"/api/activities/{activity['id']}/registrations"),
        ("get", f"/api/activities/{activity['id']}/winners"),
        ("get", f"/api/activities/{activity['id']}/stats"),
        ("get", f"/api/activities/{activity['id']}/export"),
        ("post", f"/api/activities/{activity['id']}/checkin"),
    ]:
        kwargs = {"headers": student["headers"]}
        if method != "get":
            kwargs["json"] = {}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, (method, path, response.text)
        assert response.json()["code"] == 40301


def test_organizer_cannot_touch_other_activities(client):
    org1, org2, activity = _organizers_and_activity(client)
    student = make_user(client, "stu001")
    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=student["headers"])

    # 组织者操作他人活动：编辑/取消/抽签/名单/统计/导出/签到全部 403
    for method, path in [
        ("patch", f"/api/activities/{activity['id']}"),
        ("post", f"/api/activities/{activity['id']}/cancel"),
        ("post", f"/api/activities/{activity['id']}/lottery"),
        ("get", f"/api/activities/{activity['id']}/registrations"),
        ("get", f"/api/activities/{activity['id']}/winners"),
        ("get", f"/api/activities/{activity['id']}/checkins"),
        ("get", f"/api/activities/{activity['id']}/stats"),
        ("get", f"/api/activities/{activity['id']}/export"),
        ("post", f"/api/activities/{activity['id']}/checkin"),
    ]:
        kwargs = {"headers": org2["headers"]}
        if method != "get":
            kwargs["json"] = {"code": "x"}
        response = getattr(client, method)(path, **kwargs)
        assert response.status_code == 403, (method, path, response.text)

    # 活动详情人人可看，但他人活动不可用 mine 查询
    mine = client.get("/api/activities", params={"mine": "true"}, headers=org2["headers"])
    assert mine.status_code == 200
    assert mine.json()["data"]["total"] == 0


def test_organizer_cannot_register_for_any_activity(client):
    """统一按「非 STUDENT 不可报名」实现（§2.5-1、§7.2）。"""
    org1, org2, activity = _organizers_and_activity(client)
    own = client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=org1["headers"])
    assert own.status_code == 403 and own.json()["code"] == 40301
    other_activity = create_activity(client, org2["headers"])
    other = client.post(
        f"/api/activities/{other_activity['id']}/registrations", json={}, headers=org1["headers"]
    )
    assert other.status_code == 403


def test_student_cannot_access_admin_api(client):
    student = make_user(client, "stu001")
    assert client.get("/api/admin/users", headers=student["headers"]).status_code == 403


def test_admin_passes_owner_checks(client, db):
    """ADMIN 单独放行：可操作他人活动（§5.1）。"""
    _org1, _org2, activity = _organizers_and_activity(client)
    admin = admin_session(client, db)

    stats = client.get(f"/api/activities/{activity['id']}/stats", headers=admin["headers"])
    assert stats.status_code == 200
    edited = client.patch(f"/api/activities/{activity['id']}", json={"quota": 5}, headers=admin["headers"])
    assert edited.status_code == 200
    assert edited.json()["data"]["quota"] == 5


def test_qrcode_permission_isolation(client):
    """学生查看他人二维码 403；组织者取他人报名的二维码同样 403（§5.5）。"""
    org1 = make_user(client, "org1", "ORGANIZER")
    activity = create_activity(client, org1["headers"])
    stu1, stu2 = create_students(client, 2)

    client.post(f"/api/activities/{activity['id']}/registrations", json={}, headers=stu1["headers"])
    reg_id = client.get("/api/me/registrations", headers=stu1["headers"]).json()["data"]["items"][0]["id"]

    other = client.get(f"/api/registrations/{reg_id}/qrcode", headers=stu2["headers"])
    assert other.status_code == 403 and other.json()["code"] == 40301

    own = client.get(f"/api/registrations/{reg_id}/qrcode", headers=stu1["headers"])
    assert own.status_code == 400  # 未抽签非中签 40001
    assert own.json()["code"] == 40001

    organizer = client.get(f"/api/registrations/{reg_id}/qrcode", headers=org1["headers"])
    assert organizer.status_code == 400
