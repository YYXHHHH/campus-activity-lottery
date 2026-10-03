"""FR-1 认证与用户（§2.3、§10.1 test_register_login）。"""

from __future__ import annotations

from helpers import admin_session, create_admin, DEFAULT_PASSWORD, login, make_user, register


def test_register_login(client, db):
    """注册成功 → 重复 409 → 错密 401（统一文案）→ token 访问 /me。"""
    response = register(client, "2023001", "STUDENT", "张三")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["username"] == "2023001"
    assert data["role"] == "STUDENT"
    assert "password_hash" not in data and "password" not in data

    duplicate = register(client, "2023001", "STUDENT", "李四")
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == 40901
    assert duplicate.json()["message"] == "用户名已存在"

    wrong = client.post("/api/auth/login", json={"username": "2023001", "password": "wrongpass"})
    assert wrong.status_code == 401
    assert wrong.json()["code"] == 40102
    assert wrong.json()["message"] == "用户名或密码错误"

    unknown = client.post("/api/auth/login", json={"username": "nobody_99", "password": "123456"})
    assert unknown.status_code == 401
    assert unknown.json()["message"] == "用户名或密码错误"  # 不区分原因，防枚举

    token = login(client, "2023001")
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["data"]["real_name"] == "张三"


def test_register_validation(client):
    """用户名 4-50 位、密码 ≥6 位、role 不允许 ADMIN（§2.3-1）。"""
    short_name = client.post(
        "/api/auth/register", json={"username": "ab", "password": "123456", "real_name": "甲", "role": "STUDENT"}
    )
    assert short_name.status_code == 400 and short_name.json()["code"] == 40001

    bad_chars = client.post(
        "/api/auth/register",
        json={"username": "张三abc", "password": "123456", "real_name": "甲", "role": "STUDENT"},
    )
    assert bad_chars.status_code == 400

    short_pw = client.post(
        "/api/auth/register", json={"username": "good_name", "password": "123", "real_name": "甲", "role": "STUDENT"}
    )
    assert short_pw.status_code == 400

    as_admin = client.post(
        "/api/auth/register", json={"username": "evil001", "password": "123456", "real_name": "甲", "role": "ADMIN"}
    )
    assert as_admin.status_code == 400 and as_admin.json()["code"] == 40001


def test_login_without_token_and_tampered_token(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me").json()["code"] == 40101

    make_user(client, "stu001")
    tampered = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert tampered.status_code == 401 and tampered.json()["code"] == 40101


def test_disabled_user_blocked_on_login_and_request(client, db):
    """禁用后：登录 40101；已登录用户的下一次请求同样被拒（§2.3-5、FR-1.7）。"""
    admin = admin_session(client, db)
    student = make_user(client, "stu001")

    user_row = client.get("/api/admin/users", headers=admin["headers"], params={"keyword": "stu001"}).json()["data"]["items"][0]
    disabled = client.patch(
        f"/api/admin/users/{user_row['id']}", json={"is_active": 0}, headers=admin["headers"]
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["is_active"] == 0

    login_response = client.post("/api/auth/login", json={"username": "stu001", "password": DEFAULT_PASSWORD})
    assert login_response.status_code == 401
    assert login_response.json()["code"] == 40101
    assert login_response.json()["message"] == "账号已被禁用"

    still_token = client.get("/api/auth/me", headers=student["headers"])
    assert still_token.status_code == 401
    assert still_token.json()["message"] == "账号已被禁用"

    re_enabled = client.patch(
        f"/api/admin/users/{user_row['id']}", json={"is_active": 1}, headers=admin["headers"]
    )
    assert re_enabled.json()["data"]["is_active"] == 1
    assert client.get("/api/auth/me", headers=student["headers"]).status_code == 200


def test_admin_account_created_by_seed_only(client, db):
    user_id = create_admin(db)
    assert user_id > 0
    assert login(client, "admin")
