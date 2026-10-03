"""配置加载：pydantic-settings 读取 .env，启动即校验密钥，并集中品牌/术语设置。

二次开发只需改这里（或 .env），无需改动业务代码。
"""

from __future__ import annotations

import json
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EXAMPLE_SECRET_KEYS = {
    "change-me",
    "change-me-to-a-random-64-hex-string",
    "your-secret-key-here",
    "dev-secret-key-change-me",
}


class Brand(BaseSettings):
    """品牌与术语设置：改 `.env` 里的 BRAND_* / UI_LABELS 即可换皮，无需改代码。"""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "校园活动抽签系统"
    # 站点全称（登录页大标题、<title>、OpenAPI 标题）
    BRAND_NAME: str = ""
    # 导航栏等处使用的短名称，留空则与 BRAND_NAME 相同
    BRAND_SHORT_NAME: str = ""
    # 主题色：#rrggbb，自动派生 hover 深色
    BRAND_COLOR: str = "#2563eb"
    # 界面术语覆盖表（JSON），例如 {"activity.unit": "会议室"}
    UI_LABELS: str = ""

    @property
    def resolved_app_name(self) -> str:
        return (self.BRAND_NAME or self.APP_NAME).strip()

    @property
    def brand_labels(self) -> dict[str, str]:
        """解析 UI_LABELS：容忍非法 JSON / 非字符串值，避免启动因配置笔误中断。"""
        raw = (self.UI_LABELS or "").strip()
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        if not isinstance(parsed, dict):
            return {}
        return {str(key): str(value) for key, value in parsed.items()}

    @model_validator(mode="after")
    def _fill_brand_defaults(self) -> "Brand":
        def filled(value: str) -> bool:
            return bool(value) and "{{" not in value

        if not filled(self.BRAND_NAME):
            self.BRAND_NAME = self.APP_NAME
        if not filled(self.BRAND_SHORT_NAME):
            self.BRAND_SHORT_NAME = self.BRAND_NAME
        return self


class Settings(Brand):
    SECRET_KEY: str = ""
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    DATABASE_URL: str = "sqlite:///./app.db"
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    AUTO_LOTTERY_INTERVAL_SECONDS: int = 30
    AUTO_LOTTERY_ENABLED: bool = True
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    key = settings.SECRET_KEY.strip()
    if len(key) < 16 or key in EXAMPLE_SECRET_KEYS:
        raise RuntimeError(
            "SECRET_KEY 缺失或为示例值：请在 .env 中配置长度 ≥ 16 的随机密钥"
            "（生成方式：python -c \"import secrets;print(secrets.token_hex(32))\"）"
        )
    settings.SECRET_KEY = key
    settings.PUBLIC_BASE_URL = settings.PUBLIC_BASE_URL.rstrip("/")
    return settings
