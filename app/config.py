"""M0 配置加载：pydantic-settings 读取 .env，启动即校验密钥。"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

EXAMPLE_SECRET_KEYS = {
    "change-me",
    "change-me-to-a-random-64-hex-string",
    "your-secret-key-here",
    "dev-secret-key-change-me",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NAME: str = "校园活动抽签系统"
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
