"""Pydantic API contracts (v2)."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    url: str = Field(min_length=3, max_length=4096)
    confirm_playlist: bool = False


class FormatOut(BaseModel):
    id: int | None = None
    label: str
    ext: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    approx_size_bytes: int | None = None
    size_is_estimate: bool = True
    audio_only: bool = False


class MediaItemOut(BaseModel):
    position: int
    kind: str
    filename: str | None = None
    width: int | None = None
    height: int | None = None


class JobOut(BaseModel):
    id: str
    status: str
    stage: str | None = None
    progress: float = 0.0
    source: str | None = None
    content_type: str
    original_url: str
    normalized_url: str
    title: str | None = None
    author: str | None = None
    duration_sec: int | None = None
    thumbnail_url: str | None = None
    item_count: int = 1
    approx_size_bytes: int | None = None
    actual_size_bytes: int | None = None
    error_code: str | None = None
    error_message: str | None = None
    delivery_method: str | None = None
    download_url: str | None = None
    telegram_file_id: str | None = None
    formats: list[FormatOut] = []
    items: list[MediaItemOut] = []
    created_at: datetime | None = None
    finished_at: datetime | None = None

    class Config:
        from_attributes = True


class StartDownloadRequest(BaseModel):
    format_id: int | None = None
    format_label: str | None = None       # alternative to format_id (e.g. "1080p")
    deliver_to_telegram: bool = False


class JobProgressEvent(BaseModel):
    job_id: str
    status: str
    stage: str | None = None
    progress: float = 0.0
    speed: float | None = None
    downloaded_bytes: int | None = None
    total_bytes: int | None = None
    eta: float | None = None


class TelegramAuthPayload(BaseModel):
    id: int
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class ProxyProfileOut(BaseModel):
    id: int
    name: str
    kind: str
    enabled: bool
    is_primary: bool
    is_backup: bool
    priority: int
    bound_sources: str | None = None
    display_meta: dict | None = None
    last_status: str
    last_latency_ms: int | None = None
    last_checked_at: datetime | None = None
    error_count: int = 0
    last_error_category: str | None = None

    class Config:
        from_attributes = True


class HttpProxyCreate(BaseModel):
    name: str
    url: str  # http(s)://user:pass@host:port or socks5://...
    is_primary: bool = False
    is_backup: bool = False
    priority: int = 100
    bound_sources: str | None = None


class XrayProfileCreate(BaseModel):
    name: str
    config_or_uri: str  # JSON config, VLESS/VMess/Trojan/SS URI, or subscription URL
    is_primary: bool = False
    is_backup: bool = False
    priority: int = 50
