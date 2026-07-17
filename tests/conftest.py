"""Pytest configuration: make the backend importable and set a test environment."""
from __future__ import annotations

import os
import sys
from pathlib import Path

# make `import app...` work
BACKEND = Path(__file__).resolve().parents[1] / "apps" / "backend"
sys.path.insert(0, str(BACKEND))

# deterministic test settings (set BEFORE app.config is imported)
os.environ.setdefault("ENV", "test")
os.environ.setdefault("SECRET_KEY", "test-secret-key-fixed-for-tests-only-0123456789")
os.environ.setdefault("BOT_TOKEN", "123456789:TEST_TOKEN_abcdefghijklmnopqrstuvwxyz012")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("PUBLIC_BASE_URL", "https://sharetube.appswire.ru")
os.environ.setdefault("CLOUD_BOT_SAFE_LIMIT_MB", "45")
os.environ.setdefault("LOCAL_BOT_SAFE_LIMIT_MB", "1900")
os.environ.setdefault("MAX_STORAGE_GB", "1")

import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
