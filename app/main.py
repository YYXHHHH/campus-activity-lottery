"""FastAPI 应用入口：路由注册、静态与模板挂载、lifespan 启动调度器。"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.branding import BRAND_CSS_PATH, BRAND_JS_PATH, build_branding, build_template_context
from app.config import get_settings
from app.database import create_all
from app.errors import ok, register_exception_handlers
from app.routers import activities, admin, auth, checkins, meta, registrations
from app.scheduler import build_scheduler

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


class TemplateStaticFiles(StaticFiles):
    """静态文件服务；对 .html 走 Jinja2 渲染，注入品牌占位符，并提供 api/brand.css|js。

    页面里可用的占位符：`{{BRAND_NAME}}`、`{{BRAND_SHORT}}`、`{{BRAND_COLOR}}`、
    `{{BRAND_PRIMARY_DARK}}`、`{{LABELS[...]}}`。改 .env 后重启即生效，无需改 HTML。
    """

    def __init__(self, *args: Any, context_builder=None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._context_builder = context_builder or build_template_context
        self._templates = Jinja2Templates(directory=str(self.directory))

    def get_path(self, scope: dict) -> str:
        """根路径（"" 或 "."）归一为 index.html；Windows 下反斜杠统一为 /。"""
        path = super().get_path(scope).replace("\\", "/").lstrip("/")
        return path if path not in ("", ".") else "index.html"

    async def get_response(self, path: str, scope: dict):
        normalized = path.replace("\\", "/").lstrip("/") or "index.html"
        if normalized == BRAND_CSS_PATH:
            palette = build_branding()["palette"]
            css = ":root{--primary:%s;--primary-dark:%s;}\n" % (
                palette["primary"],
                palette["primary_dark"],
            )
            return Response(content=css, media_type="text/css", headers={"Cache-Control": "no-store"})
        if normalized == BRAND_JS_PATH:
            script = "window.__BRAND__ = %s;\n" % json.dumps(build_branding(), ensure_ascii=False)
            return Response(
                content=script, media_type="application/javascript", headers={"Cache-Control": "no-store"}
            )
        response = await super().get_response(normalized, scope)
        if response.status_code == 200 and normalized.lower().endswith(".html"):
            template = self._templates.get_template(normalized)
            return HTMLResponse(template.render(**self._context_builder()))
        return response


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
    settings = get_settings()
    logger.info("[main] %s 启动，品牌=%s", settings.resolved_app_name, settings.BRAND_NAME)
    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.start()
        logger.info("[main] 自动抽签调度已启动，周期 %s 秒", settings.AUTO_LOTTERY_INTERVAL_SECONDS)
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


settings = get_settings()
app = FastAPI(
    title=settings.resolved_app_name,
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(activities.router)
app.include_router(registrations.router)
app.include_router(checkins.router)
app.include_router(admin.router)
app.include_router(meta.router)


@app.get("/api/health")
def health():
    return ok({"app": settings.resolved_app_name, "status": "up"})


STATIC_DIR.mkdir(parents=True, exist_ok=True)
# 放在最后：API 路由优先，其余交给静态文件与 HTML 模板
app.mount("/", TemplateStaticFiles(directory=str(STATIC_DIR), html=True), name="static")
