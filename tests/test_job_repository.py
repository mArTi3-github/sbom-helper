from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from purl_resolver.job_repository import JobRecord, JobRepository, _new_id


class MockRecord(dict):
    """Simulates asyncpg.Record for testing (supports both key and attr access)."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for k, v in kwargs.items():
            setattr(self, k, v)


@pytest.fixture
def repo():
    pool = MagicMock()
    cm = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=cm)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    cm.execute = AsyncMock()
    cm.fetchrow = AsyncMock()
    cm.fetch = AsyncMock()
    return JobRepository(pool)


class TestJobRepository:
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo):
        job_id = _new_id()
        record = JobRecord(id=job_id, type="sbom_enrich", status="queued")
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = MockRecord(
            id=job_id, type="sbom_enrich", status="queued",
            progress_current=0, progress_total=0, progress_phase=None,
            params_json=None, input_filename=None,
            result_path=None, summary_json=None, results_json=None,
            error_message=None, cancel_requested=0,
            created_at="2026-07-10T12:00:00", started_at=None, finished_at=None,
        )

        await repo.create(record)
        fetched = await repo.get(job_id)

        assert fetched is not None
        assert fetched.id == job_id
        assert fetched.status == "queued"

    @pytest.mark.asyncio
    async def test_create_and_get_with_progress_phase(self, repo):
        job_id = _new_id()
        record = JobRecord(
            id=job_id, type="sbom_enrich", status="running",
            progress_current=3, progress_total=10, progress_phase="resolving",
        )
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = MockRecord(
            id=job_id, type="sbom_enrich", status="running",
            progress_current=3, progress_total=10, progress_phase="resolving",
            params_json=None, input_filename=None,
            result_path=None, summary_json=None, results_json=None,
            error_message=None, cancel_requested=0,
            created_at="2026-07-10T12:00:00", started_at=None, finished_at=None,
        )

        await repo.create(record)
        fetched = await repo.get(job_id)

        assert fetched is not None
        assert fetched.progress_phase == "resolving"
        assert fetched.progress_current == 3
        assert fetched.progress_total == 10

    @pytest.mark.asyncio
    async def test_get_not_found(self, repo):
        repo._pool.acquire.return_value.__aenter__.return_value.fetchrow.return_value = None
        fetched = await repo.get("nonexistent")
        assert fetched is None

    @pytest.mark.asyncio
    async def test_update_status(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        await repo.update_status("job-1", "running", started_at="2026-07-10T12:00:00")
        conn.execute.assert_called_once_with(
            "UPDATE jobs SET status = $1, started_at = $2 WHERE id = $3",
            "running", "2026-07-10T12:00:00", "job-1",
        )

    @pytest.mark.asyncio
    async def test_list_all(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.list(limit=10, offset=0)
        conn.fetch.assert_called_once_with(
            "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2",
            10, 0,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_list_with_type_filter(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.list(type_filter="sbom_enrich", limit=5, offset=0)
        conn.fetch.assert_called_once_with(
            "SELECT * FROM jobs WHERE type = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3",
            "sbom_enrich", 5, 0,
        )
        assert results == []

    @pytest.mark.asyncio
    async def test_delete_success(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.execute.return_value = "DELETE 1"
        result = await repo.delete("job-1")
        assert result is True

    @pytest.mark.asyncio
    async def test_delete_not_found(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.execute.return_value = "DELETE 0"
        result = await repo.delete("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_queued(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_queued()
        assert results == []

    @pytest.mark.asyncio
    async def test_get_stuck_running(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_stuck_running()
        assert results == []

    @pytest.mark.asyncio
    async def test_get_expired(self, repo):
        conn = repo._pool.acquire.return_value.__aenter__.return_value
        conn.fetch.return_value = []
        results = await repo.get_expired(ttl_hours=24)
        assert results == []
