"""API integration test with FastAPI TestClient, sqlite, stubbed queue & auth."""
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool


@pytest.fixture
async def client(monkeypatch):
    from app.db import Base
    from app import models  # noqa: F401

    engine = create_async_engine("sqlite+aiosqlite:///:memory:",
                                 connect_args={"check_same_thread": False}, poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    # stub the queue so no Redis is needed
    import app.routers.jobs as jobs_router
    enqueued = []

    async def fake_enqueue_analyze(job_id):
        enqueued.append(("analyze", job_id))

    async def fake_enqueue_download(job_id):
        enqueued.append(("download", job_id))

    monkeypatch.setattr(jobs_router, "enqueue_analyze", fake_enqueue_analyze)
    monkeypatch.setattr(jobs_router, "enqueue_download", fake_enqueue_download)

    from app.main import app
    from app.db import get_session
    from app.deps import get_current_user, rate_limit_guard
    from app.models import User

    async def override_session():
        async with factory() as s:
            yield s

    # create a user and force auth to it
    async with factory() as s:
        u = User(display_name="tester")
        s.add(u)
        await s.commit()
        uid = u.id

    async def override_user():
        async with factory() as s:
            return await s.get(User, uid)

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[rate_limit_guard] = lambda: None

    from httpx import ASGITransport, AsyncClient
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c._enqueued = enqueued
        yield c

    app.dependency_overrides.clear()
    await engine.dispose()


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


async def test_analyze_creates_job_and_enqueues(client):
    r = await client.post("/api/analyze", json={"url": "https://youtu.be/abcdef"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert body["normalized_url"].startswith("https://youtu.be/")
    assert ("analyze", body["id"]) in client._enqueued


async def test_analyze_rejects_ssrf(client):
    r = await client.post("/api/analyze", json={"url": "http://169.254.169.254/latest/"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] in ("private_ip", "blocked_host")


async def test_get_job_404_for_other(client):
    r = await client.get("/api/jobs/nonexistent")
    assert r.status_code == 404
