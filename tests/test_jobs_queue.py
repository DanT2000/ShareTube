"""Job creation limits, dedup, and cancellation-transition tests (async sqlite)."""
import pytest

from _dbutil import make_session_factory


async def test_create_job_validates_url():
    from app.models import User
    from app.services import jobs as jobs_svc

    factory, engine = await make_session_factory()
    async with factory() as s:
        u = User(display_name="t")
        s.add(u)
        await s.flush()
        with pytest.raises(jobs_svc.JobError):
            await jobs_svc.create_job(s, user_id=u.id, raw_url="http://127.0.0.1/x")
    await engine.dispose()


async def test_create_job_dedup():
    from app.models import User
    from app.services import jobs as jobs_svc

    factory, engine = await make_session_factory()
    async with factory() as s:
        u = User(display_name="t")
        s.add(u)
        await s.flush()
        await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/abc")
        with pytest.raises(jobs_svc.JobError) as e:
            await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/abc")
        assert e.value.code == "duplicate"
    await engine.dispose()


async def test_cancel_transition():
    from app.models import JobStatus, User
    from app.services import jobs as jobs_svc

    factory, engine = await make_session_factory()
    async with factory() as s:
        u = User(display_name="t")
        s.add(u)
        await s.flush()
        job = await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/xyz")
        await jobs_svc.transition(s, job, JobStatus.CANCELLED, stage="cancelled")
        assert job.status == "cancelled"
        assert job.finished_at is not None
    await engine.dispose()


async def test_active_limit(monkeypatch):
    from app.config import settings
    from app.models import User
    from app.services import jobs as jobs_svc

    monkeypatch.setattr(settings, "MAX_ACTIVE_JOBS_PER_USER", 1)
    monkeypatch.setattr(settings, "MAX_QUEUED_JOBS_PER_USER", 1)
    factory, engine = await make_session_factory()
    async with factory() as s:
        u = User(display_name="t")
        s.add(u)
        await s.flush()
        await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/a")
        await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/b")
        with pytest.raises(jobs_svc.JobError) as e:
            await jobs_svc.create_job(s, user_id=u.id, raw_url="https://youtu.be/c")
        assert e.value.code == "too_many_active"
    await engine.dispose()
