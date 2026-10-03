"""M8 自动抽签调度。"""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import Activity
from app.services.lottery import run_lottery

logger = logging.getLogger(__name__)


def scan_due_activities() -> None:
    """周期扫描到期活动并逐个委托 run_lottery，单活动失败不影响其他活动。"""
    db = SessionLocal()
    try:
        due_ids = db.scalars(
            select(Activity.id).where(
                Activity.status == "PUBLISHED", Activity.signup_deadline <= utcnow()
            )
        ).all()
        for activity_id in due_ids:
            try:
                run_lottery(db, activity_id)
            except Exception:
                db.rollback()
                logger.exception("[scheduler] 自动抽签失败 activity_id=%s", activity_id)
    except Exception:
        logger.exception("[scheduler] 扫描任务异常")
    finally:
        db.close()


def build_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.AUTO_LOTTERY_ENABLED:
        logger.info("[scheduler] AUTO_LOTTERY_ENABLED=false，跳过调度器注册")
        return None

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        scan_due_activities,
        "interval",
        seconds=settings.AUTO_LOTTERY_INTERVAL_SECONDS,
        max_instances=1,
        coalesce=True,
        id="auto-lottery",
    )
    return scheduler
