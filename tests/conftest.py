"""pytest 夹具：内存 SQLite + TestClient（§10.1）。"""

from __future__ import annotations

import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-please-do-not-use-in-production")
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTO_LOTTERY_ENABLED"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False, "timeout": 30},
    poolclass=StaticPool,
    future=True,
)
TestingSessionLocal = sessionmaker(bind=test_engine, expire_on_commit=False, future=True)


@pytest.fixture(autouse=True)
def _fresh_schema():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    # 不使用 with，避免触发 lifespan（建表/调度器）污染真实库
    yield TestClient(app)
    app.dependency_overrides.clear()
