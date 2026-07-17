"""Storage TTL cleanup and over-cap eviction tests (async sqlite)."""
from datetime import datetime, timedelta, timezone

import pytest

from _dbutil import make_session_factory


class _FakeProvider:
    """Records deletions instead of touching the filesystem."""
    name = "local"

    def __init__(self):
        self.deleted = []

    async def delete(self, rel_path):
        self.deleted.append(rel_path)

    async def save(self, *a, **k):  # unused here
        raise NotImplementedError


async def test_cleanup_expired(monkeypatch):
    from app.models import StoredFile
    from app.services import storage_service

    factory, engine = await make_session_factory()
    fake = _FakeProvider()
    monkeypatch.setattr(storage_service, "get_storage_provider", lambda: fake)

    now = datetime.now(timezone.utc)
    async with factory() as s:
        s.add(StoredFile(provider="local", rel_path="a/x", filename="x.mp4", size_bytes=10,
                         expires_at=now - timedelta(hours=1)))
        s.add(StoredFile(provider="local", rel_path="b/y", filename="y.mp4", size_bytes=10,
                         expires_at=now + timedelta(hours=5)))
        await s.commit()

    async with factory() as s:
        n = await storage_service.cleanup_expired(s)
        await s.commit()
    assert n == 1
    assert fake.deleted == ["a/x"]

    await engine.dispose()


async def test_enforce_cap_evicts_oldest(monkeypatch):
    from app.config import settings
    from app.models import StoredFile
    from app.services import storage_service

    factory, engine = await make_session_factory()
    fake = _FakeProvider()
    monkeypatch.setattr(storage_service, "get_storage_provider", lambda: fake)
    monkeypatch.setattr(settings, "MAX_STORAGE_GB", 100 / 1024 / 1024 / 1024)  # ~100 bytes cap

    async with factory() as s:
        for i in range(4):
            s.add(StoredFile(provider="local", rel_path=f"p/{i}", filename=f"{i}.bin",
                             size_bytes=50))
        await s.commit()

    async with factory() as s:
        freed = await storage_service.enforce_storage_cap(s)
        await s.commit()
    # total 200 bytes, cap ~100 -> must evict until <=100 => evict 2 oldest (=100 freed)
    assert freed >= 100
    assert len(fake.deleted) >= 2

    await engine.dispose()
