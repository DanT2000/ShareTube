"""SQLAlchemy 2.0 ORM models — full ShareTube schema."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base

# JSONB on PostgreSQL, plain JSON elsewhere (e.g. SQLite in tests).
JSONVariant = JSON().with_variant(JSONB, "postgresql")


def _uuid() -> str:
    return uuid.uuid4().hex


class JobStatus(str, enum.Enum):
    PENDING = "pending"          # created, awaiting analysis
    ANALYZING = "analyzing"      # fetching metadata
    ANALYZED = "analyzed"        # metadata ready, awaiting format choice
    QUEUED = "queued"            # format chosen, in queue
    DOWNLOADING = "downloading"
    MERGING = "merging"
    CONVERTING = "converting"
    UPLOADING = "uploading"      # delivering to Telegram / storage
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentType(str, enum.Enum):
    VIDEO = "video"
    SHORT = "short"           # Shorts/Reels/TikTok vertical
    AUDIO = "audio"
    PHOTO = "photo"
    PHOTO_CAROUSEL = "photo_carousel"
    MIXED = "mixed"
    PLAYLIST = "playlist"
    LIVE = "live"
    UNKNOWN = "unknown"


class DeliveryMethod(str, enum.Enum):
    CLOUD_BOT = "cloud_bot"
    LOCAL_BOT = "local_bot"
    SIGNED_LINK = "signed_link"
    ZIP_LINK = "zip_link"
    CACHED_FILE_ID = "cached_file_id"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    quota_daily_jobs: Mapped[int | None] = mapped_column(Integer)  # None = default
    quota_daily_bytes: Mapped[int | None] = mapped_column(BigInteger)

    telegram_accounts: Mapped[list[TelegramAccount]] = relationship(back_populates="user")
    jobs: Mapped[list[DownloadJob]] = relationship(back_populates="user")


class TelegramAccount(Base, TimestampMixin):
    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    username: Mapped[str | None] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(255))
    language_code: Mapped[str | None] = mapped_column(String(16))

    user: Mapped[User] = relationship(back_populates="telegram_accounts")


class DownloadJob(Base, TimestampMixin):
    __tablename__ = "download_jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    origin: Mapped[str] = mapped_column(String(16), default="web")  # web | bot | miniapp

    original_url: Mapped[str] = mapped_column(Text)
    normalized_url: Mapped[str] = mapped_column(Text)
    source: Mapped[str | None] = mapped_column(String(64), index=True)  # youtube, tiktok, ...
    extractor: Mapped[str | None] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(32), default=ContentType.UNKNOWN.value)

    status: Mapped[str] = mapped_column(String(32), default=JobStatus.PENDING.value, index=True)
    progress: Mapped[float] = mapped_column(Float, default=0.0)  # 0..100
    stage: Mapped[str | None] = mapped_column(String(32))

    selected_format_id: Mapped[int | None] = mapped_column(ForeignKey("selected_formats.id"))
    approx_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    actual_size_bytes: Mapped[int | None] = mapped_column(BigInteger)

    stored_file_id: Mapped[int | None] = mapped_column(ForeignKey("stored_files.id"))
    telegram_file_id: Mapped[str | None] = mapped_column(String(255))
    delivery_method: Mapped[str | None] = mapped_column(String(32))

    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)  # user-safe russian message
    retry_count: Mapped[int] = mapped_column(Integer, default=0)

    # delivery context for bot-origin jobs (set when created from Telegram)
    deliver_to_telegram: Mapped[bool] = mapped_column(Boolean, default=False)
    tg_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    tg_progress_message_id: Mapped[int | None] = mapped_column(BigInteger)

    outbound_profile_id: Mapped[int | None] = mapped_column(ForeignKey("proxy_profiles.id"))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="jobs")
    media_sources: Mapped[list[MediaSource]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


class MediaSource(Base, TimestampMixin):
    __tablename__ = "media_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("download_jobs.id", ondelete="CASCADE"), index=True)
    title: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(512))
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(32), default=ContentType.UNKNOWN.value)
    item_count: Mapped[int] = mapped_column(Integer, default=1)
    is_live: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_meta: Mapped[dict | None] = mapped_column(JSONVariant)

    job: Mapped[DownloadJob] = relationship(back_populates="media_sources")
    items: Mapped[list[MediaItem]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    formats: Mapped[list[SelectedFormat]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class MediaItem(Base):
    __tablename__ = "media_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("media_sources.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)  # preserves carousel order
    kind: Mapped[str] = mapped_column(String(16), default="photo")  # photo | video | audio
    url: Mapped[str | None] = mapped_column(Text)
    filename: Mapped[str | None] = mapped_column(String(512))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    duration_sec: Mapped[int | None] = mapped_column(Integer)

    source: Mapped[MediaSource] = relationship(back_populates="items")


class SelectedFormat(Base):
    __tablename__ = "selected_formats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("media_sources.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(64))  # "1080p", "audio", "auto", ...
    format_selector: Mapped[str | None] = mapped_column(Text)  # yt-dlp -f value (server-built only)
    ext: Mapped[str | None] = mapped_column(String(16))
    vcodec: Mapped[str | None] = mapped_column(String(64))
    acodec: Mapped[str | None] = mapped_column(String(64))
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    fps: Mapped[float | None] = mapped_column(Float)
    approx_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    size_is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)
    audio_only: Mapped[bool] = mapped_column(Boolean, default=False)

    source: Mapped[MediaSource] = relationship(back_populates="formats")


class StoredFile(Base, TimestampMixin):
    __tablename__ = "stored_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("download_jobs.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16), default="local")  # local | s3
    opaque_token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=_uuid)
    rel_path: Mapped[str] = mapped_column(Text)  # relative path inside storage dir / s3 key
    filename: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str | None] = mapped_column(String(128))
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    is_zip: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_access_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DeliveryAttempt(Base, TimestampMixin):
    __tablename__ = "delivery_attempts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("download_jobs.id"), index=True)
    method: Mapped[str] = mapped_column(String(32))
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    detail: Mapped[str | None] = mapped_column(Text)


class TelegramFileCache(Base, TimestampMixin):
    __tablename__ = "telegram_file_cache"
    __table_args__ = (UniqueConstraint("content_hash", "delivery_kind", name="uq_cache_hash_kind"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content_hash: Mapped[str] = mapped_column(String(128), index=True)  # source+format signature
    delivery_kind: Mapped[str] = mapped_column(String(16), default="video")  # video|audio|photo|document
    telegram_file_id: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    title: Mapped[str | None] = mapped_column(Text)


class DownloadLink(Base, TimestampMixin):
    __tablename__ = "download_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stored_file_id: Mapped[int] = mapped_column(ForeignKey("stored_files.id", ondelete="CASCADE"))
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True, default=_uuid)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    max_downloads: Mapped[int | None] = mapped_column(Integer)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)


class CookieProfile(Base, TimestampMixin):
    __tablename__ = "cookie_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)  # youtube, instagram, vk...
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # encrypted cookie blob (Fernet). NEVER returned via API, never logged.
    encrypted_data: Mapped[bytes | None] = mapped_column()
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_status: Mapped[str] = mapped_column(String(16), default="unknown")  # ok|failing|unknown


class ProxyProfile(Base, TimestampMixin):
    """Outbound network profile: HTTP/SOCKS proxy or Xray. Secrets encrypted."""
    __tablename__ = "proxy_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))  # human label, e.g. "xray-main"
    kind: Mapped[str] = mapped_column(String(16), default="http")  # http | socks5 | xray
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    is_backup: Mapped[bool] = mapped_column(Boolean, default=False)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    bound_sources: Mapped[str | None] = mapped_column(String(512))  # csv of sources or null=all

    # For http/socks: encrypted full URL. For xray: encrypted config json / URI.
    encrypted_config: Mapped[bytes | None] = mapped_column()
    # Safe display metadata (masked host/port/protocol) — OK to return via API.
    display_meta: Mapped[dict | None] = mapped_column(JSONVariant)

    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(16), default="unknown")  # ok|failing|unknown
    last_latency_ms: Mapped[int | None] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error_category: Mapped[str | None] = mapped_column(String(64))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    actor: Mapped[str | None] = mapped_column(String(128))  # admin id / system
    action: Mapped[str] = mapped_column(String(128), index=True)
    target: Mapped[str | None] = mapped_column(String(255))
    detail: Mapped[dict | None] = mapped_column(JSONVariant)
    ip: Mapped[str | None] = mapped_column(String(64))


class SystemSetting(Base, TimestampMixin):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
