"""Centralised configuration. All limits and secrets live here — never scattered in code."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # --- core ---
    ENV: Literal["dev", "prod", "test"] = "prod"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8989
    PUBLIC_BASE_URL: str = "https://sharetube.appswire.ru"
    SECRET_KEY: str = "CHANGE_ME_dev_only_secret_key_change_in_prod"
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool = True

    # --- database / redis ---
    DATABASE_URL: str = "postgresql+asyncpg://sharetube:sharetube@postgres:5432/sharetube"
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://sharetube:sharetube@postgres:5432/sharetube"
    REDIS_URL: str = "redis://redis:6379/0"

    # --- telegram ---
    BOT_TOKEN: str = ""
    BOT_USERNAME: str = "sharetube_bot"
    TELEGRAM_WEBHOOK_SECRET: str = ""
    TELEGRAM_USE_WEBHOOK: bool = False
    TELEGRAM_API_BASE: str = "https://api.telegram.org"
    TELEGRAM_ADMIN_IDS: str = ""  # comma-separated telegram user ids

    # --- local bot api (optional) ---
    LOCAL_BOT_API_ENABLED: bool = False
    LOCAL_BOT_API_BASE: str = "http://telegram-bot-api:8081"
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""
    # Route Telegram Bot API traffic through this proxy (cloud API may be blocked
    # on the host's direct route). Empty = direct. Ignored when Local Bot API is used.
    TELEGRAM_PROXY_URL: str = ""

    # --- delivery limits (MB) ---
    CLOUD_BOT_SAFE_LIMIT_MB: int = 45
    LOCAL_BOT_SAFE_LIMIT_MB: int = 1900
    MAX_DOWNLOAD_SIZE_MB: int = 10000
    DOWNLOAD_LINK_TTL_HOURS: int = 24

    # --- queue / limits ---
    MAX_ACTIVE_JOBS_PER_USER: int = 2
    MAX_QUEUED_JOBS_PER_USER: int = 5
    MAX_GLOBAL_DOWNLOADS: int = 3
    MAX_GLOBAL_TRANSCODES: int = 1
    MAX_PLAYLIST_ITEMS: int = 20
    JOB_TIMEOUT_MINUTES: int = 120
    MAX_URL_LENGTH: int = 2048
    PLAYLISTS_ENABLED: bool = False

    # --- storage ---
    STORAGE_PROVIDER: Literal["local", "s3"] = "local"
    STORAGE_DIR: str = "/data/storage"
    TMP_DIR: str = "/data/tmp"
    MAX_STORAGE_GB: float = 2.0
    DOWNLOAD_RATE_LIMIT_KBPS: int = 0  # 0 = unlimited

    # --- s3 (optional) ---
    S3_ENDPOINT: str = ""
    S3_BUCKET: str = ""
    S3_REGION: str = "us-east-1"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""

    # --- outbound / proxy ---
    OUTBOUND_REQUIRED: bool = True  # never fall back to direct on proxy failure
    # Primary outbound: AmneziaWG obfuscated tunnel (bypasses upstream throttling that
    # kills the plain Xray/Reality route). XRAY_SOCKS_URL names the seeded primary socks.
    XRAY_SOCKS_URL: str = "socks5h://amneziawg:1080"
    XRAY_BACKUP_SOCKS_URL: str = "socks5h://xray:1080"
    YTDLP_PROXY_URL: str = ""
    GALLERY_DL_PROXY_URL: str = ""
    DIRECT_DOWNLOAD_PROXY_URL: str = ""
    NO_PROXY: str = "127.0.0.1,localhost,postgres,redis,xray,telegram-bot-api"

    # --- security ---
    DOMAIN_ALLOWLIST: str = ""  # empty = allow all public domains
    DOMAIN_DENYLIST: str = ""
    MAX_REDIRECTS: int = 5
    RATE_LIMIT_PER_MINUTE: int = 30
    ADMIN_SESSION_TTL_HOURS: int = 12
    CORS_ORIGINS: str = "https://sharetube.appswire.ru"

    # --- monitoring (optional) ---
    SENTRY_DSN: str = ""
    PROMETHEUS_ENABLED: bool = False

    @field_validator("PUBLIC_BASE_URL")
    @classmethod
    def _strip_slash(cls, v: str) -> str:
        return v.rstrip("/")

    # convenience byte limits
    @property
    def telegram_proxy(self) -> str | None:
        """Proxy for cloud Bot API calls; None when using Local Bot API or direct."""
        if self.LOCAL_BOT_API_ENABLED:
            return None
        return self.TELEGRAM_PROXY_URL or None

    @property
    def cloud_bot_safe_bytes(self) -> int:
        return self.CLOUD_BOT_SAFE_LIMIT_MB * 1024 * 1024

    @property
    def local_bot_safe_bytes(self) -> int:
        return self.LOCAL_BOT_SAFE_LIMIT_MB * 1024 * 1024

    @property
    def max_download_bytes(self) -> int:
        return self.MAX_DOWNLOAD_SIZE_MB * 1024 * 1024

    @property
    def max_storage_bytes(self) -> int:
        return int(self.MAX_STORAGE_GB * 1024 * 1024 * 1024)

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.TELEGRAM_ADMIN_IDS.split(",") if x.strip().isdigit()}

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    @property
    def domain_allowlist_set(self) -> set[str]:
        return {d.strip().lower() for d in self.DOMAIN_ALLOWLIST.split(",") if d.strip()}

    @property
    def domain_denylist_set(self) -> set[str]:
        return {d.strip().lower() for d in self.DOMAIN_DENYLIST.split(",") if d.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
