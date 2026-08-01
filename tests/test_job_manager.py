from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from purl_resolver.job_manager import JobManager, _JobProgressReporter
from purl_resolver.job_repository import JobRecord
from purl_resolver.resolver.interface import Resolution
from purl_resolver.service import PurlResolutionService
from purl_resolver.storage.inmemory import InMemoryCache
from tests.helpers import FakeResolver


@pytest.fixture
def mock_repo():
    mgr = MagicMock()
    mgr.create = AsyncMock()
    mgr.get = AsyncMock()
    mgr.list = AsyncMock()
    mgr.update_status = AsyncMock()
    mgr.update_progress = AsyncMock()
    mgr.delete = AsyncMock()
    mgr.get_queued = AsyncMock()
    mgr.get_stuck_running = AsyncMock()
    mgr.get_expired = AsyncMock()
    return mgr


@pytest.fixture
def mock_resolution_service():
    return MagicMock()


@pytest.fixture
def manager(mock_repo, mock_resolution_service):
    mgr = JobManager.__new__(JobManager)
    mgr._repo = mock_repo
    mgr._resolution_service = mock_resolution_service
    mgr._job_ttl_hours = 24
    mgr._queue = MagicMock()
    mgr._queue.put = AsyncMock()
    mgr._queue.get = AsyncMock()
    mgr._queue.task_done = MagicMock()
    mgr._running_tasks = {}
    mgr._worker_task = None
    mgr._cleanup_task = None
    return mgr


class TestJobManager:

    @patch("purl_resolver.job_manager._new_id", return_value="test-job-123")
    @patch("purl_resolver.job_manager.JOBS_DIR", new_callable=MagicMock)
    async def test_create_job(self, mock_jobs_dir, mock_new_id, manager):
        mock_jobs_dir.__truediv__.return_value.__truediv__.return_value = MagicMock()
        mock_job_dir = MagicMock()
        mock_jobs_dir.__truediv__.return_value = mock_job_dir
        mock_input_path = MagicMock()
        mock_job_dir.__truediv__.return_value = mock_input_path

        manager._repo.create.return_value = None

        input_bytes = b'{"key": "value"}'
        record = await manager.create_job(
            input_bytes=input_bytes,
            input_filename="test.json",
            params={"foo": "bar"},
        )

        assert record.id == "test-job-123"
        assert record.type == "sbom_enrich"
        assert record.status == "queued"
        assert record.input_filename == "test.json"
        assert json.loads(record.params_json) == {"foo": "bar"}

        mock_job_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        mock_input_path.write_bytes.assert_called_once_with(input_bytes)
        manager._repo.create.assert_called_once_with(record)
        manager._queue.put.assert_called_once_with("test-job-123")

    async def test_get_job(self, manager):
        expected = JobRecord(id="j1", type="sbom_enrich", status="running")
        manager._repo.get.return_value = expected

        result = await manager.get_job("j1")
        assert result is expected
        manager._repo.get.assert_called_once_with("j1")

    async def test_get_job_not_found(self, manager):
        manager._repo.get.return_value = None
        result = await manager.get_job("nonexistent")
        assert result is None

    async def test_list_jobs(self, manager):
        records = [
            JobRecord(id="j1", type="sbom_enrich", status="completed"),
            JobRecord(id="j2", type="sbom_enrich", status="running"),
        ]
        manager._repo.list.return_value = records

        result = await manager.list_jobs(limit=10, offset=0)
        assert result == records
        manager._repo.list.assert_called_once_with(
            type_filter="sbom_enrich", limit=10, offset=0
        )

    async def test_cancel_job_sets_flag(self, manager):
        record = JobRecord(id="j1", type="sbom_enrich", status="running")
        manager._repo.get.return_value = record

        result = await manager.cancel_job("j1")
        assert result is True
        manager._repo.update_status.assert_called_once()
        args, kwargs = manager._repo.update_status.call_args
        assert args == ("j1", "cancelled")
        assert kwargs.get("cancel_requested") == 1
        assert "finished_at" in kwargs

    async def test_cancel_job_already_terminal(self, manager):
        for status in ("completed", "failed", "cancelled"):
            record = JobRecord(id="j1", type="sbom_enrich", status=status)
            manager._repo.get.return_value = record
            manager._repo.update_status.reset_mock()

            result = await manager.cancel_job("j1")
            assert result is False
            manager._repo.update_status.assert_not_called()

    async def test_cancel_job_not_found(self, manager):
        manager._repo.get.return_value = None
        result = await manager.cancel_job("nonexistent")
        assert result is False

    async def test_delete_job_removes_files_and_record(self, manager, tmp_path):
        job_dir = tmp_path / "test-job-456"
        job_dir.mkdir(parents=True)
        (job_dir / "input.json").write_text("{}")

        record = JobRecord(id="test-job-456", type="sbom_enrich", status="completed")
        manager._repo.get.return_value = record
        manager._repo.delete.return_value = True

        with patch("purl_resolver.job_manager.JOBS_DIR", tmp_path):
            result = await manager.delete_job("test-job-456")

        assert result is True
        assert not job_dir.exists()
        manager._repo.delete.assert_called_once_with("test-job-456")

    async def test_delete_job_not_found(self, manager):
        manager._repo.get.return_value = None
        result = await manager.delete_job("nonexistent")
        assert result is False
        manager._repo.delete.assert_not_called()

    async def test_start_recovers_stuck_running(self, manager):
        stuck = [
            JobRecord(id="stuck-1", type="sbom_enrich", status="running"),
            JobRecord(id="stuck-2", type="sbom_enrich", status="running"),
        ]
        manager._repo.get_stuck_running.return_value = stuck
        manager._repo.get_queued.return_value = []

        with (
            patch.object(manager, "_run_worker"),
            patch.object(manager, "_run_cleanup"),
            patch("purl_resolver.job_manager.JOBS_DIR") as mock_jobs_dir,
            patch("purl_resolver.job_manager._now", return_value="2026-07-10T12:00:00"),
        ):
            mock_jobs_dir.mkdir = MagicMock()
            await manager.start()

        assert manager._repo.update_status.call_count == 2
        manager._repo.update_status.assert_any_call(
            "stuck-1", "failed",
            error_message="Server restarted during processing",
            finished_at="2026-07-10T12:00:00",
        )
        manager._repo.update_status.assert_any_call(
            "stuck-2", "failed",
            error_message="Server restarted during processing",
            finished_at="2026-07-10T12:00:00",
        )

    async def test_start_re_enqueues_queued_jobs(self, manager):
        manager._repo.get_stuck_running.return_value = []
        queued = [
            JobRecord(id="q-1", type="sbom_enrich", status="queued"),
            JobRecord(id="q-2", type="sbom_enrich", status="queued"),
        ]
        manager._repo.get_queued.return_value = queued

        with (
            patch.object(manager, "_run_worker"),
            patch.object(manager, "_run_cleanup"),
            patch("purl_resolver.job_manager.JOBS_DIR") as mock_jobs_dir,
        ):
            mock_jobs_dir.mkdir = MagicMock()
            await manager.start()

        assert manager._queue.put.call_count == 2
        manager._queue.put.assert_any_call("q-1")
        manager._queue.put.assert_any_call("q-2")

    async def test_start_creates_worker_and_cleanup_tasks(self, manager):
        manager._repo.get_stuck_running.return_value = []
        manager._repo.get_queued.return_value = []

        with (
            patch.object(manager, "_run_worker"),
            patch.object(manager, "_run_cleanup"),
            patch("purl_resolver.job_manager.JOBS_DIR") as mock_jobs_dir,
        ):
            await manager.start()

        mock_jobs_dir.mkdir.assert_called_once_with(parents=True, exist_ok=True)

    async def test_stop_cancels_worker_and_cleanup(self, manager):
        async def never_ending():
            await asyncio.Event().wait()

        worker_task = asyncio.create_task(never_ending())
        cleanup_task = asyncio.create_task(never_ending())
        await asyncio.sleep(0)

        manager._worker_task = worker_task
        manager._cleanup_task = cleanup_task

        await manager.stop()

        assert worker_task.cancelled()
        assert cleanup_task.cancelled()


class FakeClock:
    def __init__(self, values: list[float]) -> None:
        self._values = list(values)

    def __call__(self) -> float:
        return self._values.pop(0)


class TestJobProgressReporter:

    @pytest.mark.asyncio
    async def test_throttles_intermediate_writes(self, mock_repo) -> None:
        # Clock values consumed in this order:
        #   initial write, 2 skipped checks, throttle-expired write, final write
        clock = FakeClock([0.0, 0.0, 0.1, 3.0, 9.0, 9.0])
        reporter = _JobProgressReporter(mock_repo, "j1", monotonic=clock)

        await reporter.on_resolved(0, 10)    # initial -> write (0, 10)
        await reporter.on_resolved(1, 10)    # 0.0 - 0.0 < 2 -> skip
        await reporter.on_resolved(2, 10)    # 0.1 - 0.0 < 2 -> skip
        await reporter.on_resolved(5, 10)    # 3.0 - 0.1 >= 2 -> write (5, 10)
        await reporter.on_resolved(10, 10)   # current == total -> forced write

        writes = [
            c.kwargs for c in mock_repo.update_progress.call_args_list
            if "progress_current" in c.kwargs
        ]
        assert writes == [
            {"progress_current": 0, "progress_total": 10},
            {"progress_current": 5, "progress_total": 10},
            {"progress_current": 10, "progress_total": 10},
        ]

    @pytest.mark.asyncio
    async def test_phase_writes_unconditionally(self, mock_repo) -> None:
        reporter = _JobProgressReporter(mock_repo, "j1", monotonic=lambda: 1.0)

        await reporter.on_phase("parsing")
        await reporter.on_phase("resolving")

        assert mock_repo.update_progress.call_count == 2
        mock_repo.update_progress.assert_any_call("j1", progress_phase="parsing")
        mock_repo.update_progress.assert_any_call("j1", progress_phase="resolving")

    @pytest.mark.asyncio
    async def test_db_error_is_swallowed(self, mock_repo) -> None:
        mock_repo.update_progress.side_effect = RuntimeError("db down")
        reporter = _JobProgressReporter(mock_repo, "j1")

        await reporter.on_phase("resolving")
        await reporter.on_resolved(0, 10)


class TestProcessJobProgress:

    @pytest.mark.asyncio
    async def test_process_job_reports_progress(self, manager, mock_repo, tmp_path) -> None:
        record = JobRecord(
            id="j1", type="sbom_enrich", status="queued",
            params_json=json.dumps({"remove_unresolved_no_subcomponents": False}),
        )
        mock_repo.get.return_value = record
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            ),
        )
        manager._resolution_service = PurlResolutionService(InMemoryCache(), [resolver])

        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "library", "name": "requests", "version": "2.31.0",
                    "purl": "pkg:pypi/requests@2.31.0",
                },
                {
                    "type": "library", "name": "flask", "version": "3.0.0",
                    "purl": "pkg:pypi/flask@3.0.0",
                },
            ],
        }
        with patch("purl_resolver.job_manager.JOBS_DIR", tmp_path):
            (tmp_path / "j1").mkdir(parents=True)
            (tmp_path / "j1" / "input.json").write_text(json.dumps(sbom))
            await manager._process_job("j1")

        progress_calls = [
            c.kwargs for c in mock_repo.update_progress.call_args_list
            if "progress_" in " | ".join(c.kwargs)
        ]
        phases = [k["progress_phase"] for k in progress_calls if "progress_phase" in k]
        totals = [k["progress_total"] for k in progress_calls if "progress_total" in k]
        last_progress = [k for k in progress_calls if "progress_current" in k][-1]

        assert phases == ["parsing", "resolving", "enriching"]
        assert totals and totals[0] == 2
        assert last_progress["progress_current"] == 2
        assert last_progress["progress_total"] == 2

        statuses = [c.args[1] for c in mock_repo.update_status.call_args_list]
        assert statuses[-1] == "completed"
