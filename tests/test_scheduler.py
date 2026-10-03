"""M8 自动抽签调度。"""

from __future__ import annotations

import time

import app.scheduler as scheduler_module
from conftest import TestingSessionLocal
from helpers import create_activity, make_user, offset


def _due_activity(client, org, title="到期活动"):
    activity = create_activity(client, org["headers"], title=title, signup_deadline=offset(seconds=1))
    time.sleep(1.4)
    return activity


def _status(db, activity_id: int) -> str:
    from app.models import Activity

    db.expire_all()
    return str(db.get(Activity, activity_id).status)


def test_scan_lots_due_activities(client, db, monkeypatch):
    monkeypatch.setattr(scheduler_module, "SessionLocal", TestingSessionLocal)
    org = make_user(client, "org1", "ORGANIZER")
    due = _due_activity(client, org)
    future = create_activity(client, org["headers"], title="未到期活动")

    scheduler_module.scan_due_activities()

    # 直接读库断言，避免 GET 详情触发兜底抽签（I-2）干扰结论
    assert _status(db, due["id"]) == "LOTTERY_DONE"
    assert _status(db, future["id"]) == "PUBLISHED"


def test_scan_is_idempotent(client, db, monkeypatch):
    monkeypatch.setattr(scheduler_module, "SessionLocal", TestingSessionLocal)
    org = make_user(client, "org1", "ORGANIZER")
    due = _due_activity(client, org)

    scheduler_module.scan_due_activities()
    ranks_before = {
        row["username"]: row["lottery_rank"]
        for row in client.get(
            f"/api/activities/{due['id']}/registrations", params={"size": 50}, headers=org["headers"]
        ).json()["data"]["items"]
    }
    scheduler_module.scan_due_activities()  # 第二次扫描不应重排名单
    ranks_after = {
        row["username"]: row["lottery_rank"]
        for row in client.get(
            f"/api/activities/{due['id']}/registrations", params={"size": 50}, headers=org["headers"]
        ).json()["data"]["items"]
    }
    assert ranks_before == ranks_after


def test_one_failure_does_not_block_others(client, db, monkeypatch):
    """单活动失败记日志后继续下一个。"""
    monkeypatch.setattr(scheduler_module, "SessionLocal", TestingSessionLocal)
    org = make_user(client, "org1", "ORGANIZER")
    broken = _due_activity(client, org, title="将失败的活动")
    healthy = _due_activity(client, org, title="正常的活动")

    calls = []

    from app.services.lottery import run_lottery as real_run_lottery

    def flaky_run_lottery(db, activity_id, *, force=False):
        calls.append(activity_id)
        if activity_id == broken["id"]:
            raise RuntimeError("模拟抽签失败")
        return real_run_lottery(db, activity_id, force=force)

    monkeypatch.setattr(scheduler_module, "run_lottery", flaky_run_lottery)
    scheduler_module.scan_due_activities()

    assert set(calls) == {broken["id"], healthy["id"]}
    assert _status(db, healthy["id"]) == "LOTTERY_DONE"
    # 失败的活动仍保持 PUBLISHED，由兜底或下次扫描重试
    assert _status(db, broken["id"]) == "PUBLISHED"


def test_scheduler_disabled_by_config(monkeypatch):
    from app.config import Settings

    settings = Settings(AUTO_LOTTERY_ENABLED=False, SECRET_KEY="x" * 32)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    assert scheduler_module.build_scheduler() is None


def test_scheduler_registers_interval_job(monkeypatch):
    from app.config import Settings

    settings = Settings(AUTO_LOTTERY_ENABLED=True, AUTO_LOTTERY_INTERVAL_SECONDS=45, SECRET_KEY="x" * 32)
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)
    scheduler = scheduler_module.build_scheduler()
    job = scheduler.get_job("auto-lottery")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 45
    assert job.max_instances == 1 and job.coalesce is True
