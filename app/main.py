"""FastAPI 应用入口：路由注册、静态挂载、lifespan 启动调度器。"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import create_all
from app.errors import ok, register_exception_handlers
from app.routers import activities, admin, auth, checkins, registrations
from app.scheduler import build_scheduler

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


def setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        handlers.append(logging.FileHandler("app.log", encoding="utf-8"))
    except OSError:  # 只读目录下退化为控制台日志
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=handlers,
        force=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    create_all()
    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.start()
        logger.info(
            "[main] 自动抽签调度已启动，周期 %s 秒", get_settings().AUTO_LOTTERY_INTERVAL_SECONDS
        )
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


settings = get_settings()
app = FastAPI(title=settings.APP_NAME, lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json")
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(activities.router)
app.include_router(registrations.router)
app.include_router(checkins.router)
app.include_router(admin.router)


@app.get("/api/health")
def health():
    return ok({"app": settings.APP_NAME, "status": "up"})


STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
