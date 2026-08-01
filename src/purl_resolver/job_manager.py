from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import asyncpg

from .job_repository import JobRecord, JobRepository, _new_id, _now
from .sbom.parser import SbomParseError
from .sbom_enrichment import SbomEnrichmentPipeline
from .service import PurlResolutionService

logger = logging.getLogger(__name__)

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "data/jobs"))

_PROGRESS_THROTTLE_SECONDS = 2.0


class _JobProgressReporter:
    """Writes pipeline progress into the jobs table, throttling DB writes.

    Forced writes happen on phase changes and on the initial (0, total) and
    final (total, total) progress events; intermediate writes are throttled
    to ``throttle_seconds`` (default 2.0, matching the frontend poll interval).
    DB errors are logged and swallowed — progress reporting never fails a job.
    """

    def __init__(
        self,
        repo: JobRepository,
        job_id: str,
        throttle_seconds: float = _PROGRESS_THROTTLE_SECONDS,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._repo = repo
        self._job_id = job_id
        self._throttle_seconds = throttle_seconds
        self._monotonic = monotonic
        self._last_write = 0.0

    async def on_phase(self, phase: str) -> None:
        await self._write(progress_phase=phase)

    async def on_resolved(self, current: int, total: int) -> None:
        if current == 0 or current == total:
            await self._write(progress_current=current, progress_total=total)
            return
        if self._monotonic() - self._last_write >= self._throttle_seconds:
            await self._write(progress_current=current, progress_total=total)

    async def _write(self, **fields: Any) -> None:
        try:
            self._last_write = self._monotonic()
            await self._repo.update_progress(self._job_id, **fields)
        except Exception:
            logger.warning("Failed to update progress for job %s", self._job_id, exc_info=True)


class JobManager:
    def __init__(
        self,
        pool: asyncpg.Pool,
        resolution_service: PurlResolutionService,
        job_ttl_hours: int = 24,
    ) -> None:
        self._repo = JobRepository(pool)
        self._resolution_service = resolution_service
        self._job_ttl_hours = job_ttl_hours
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._worker_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

        stuck = await self._repo.get_stuck_running()
        for job in stuck:
            await self._repo.update_status(
                job.id,
                "failed",
                error_message="Server restarted during processing",
                finished_at=_now(),
            )
            logger.warning("Marked stuck job %s as failed", job.id)

        queued = await self._repo.get_queued()
        for job in queued:
            await self._queue.put(job.id)
            logger.info("Re-enqueued job %s", job.id)

        self._worker_task = asyncio.create_task(self._run_worker())
        self._cleanup_task = asyncio.create_task(self._run_cleanup())

    async def stop(self) -> None:
        for task in self._running_tasks.values():
            if not task.done():
                task.cancel()
        if self._running_tasks:
            await asyncio.gather(*self._running_tasks.values(), return_exceptions=True)
            self._running_tasks.clear()
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def update_ttl(self, ttl_hours: int) -> None:
        self._job_ttl_hours = ttl_hours

    async def create_job(
        self,
        input_bytes: bytes,
        input_filename: str,
        params: dict,
    ) -> JobRecord:
        job_id = _new_id()
        job_dir = JOBS_DIR / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        input_path = job_dir / "input.json"
        input_path.write_bytes(input_bytes)

        record = JobRecord(
            id=job_id,
            type="sbom_enrich",
            status="queued",
            params_json=json.dumps(params),
            input_filename=input_filename,
        )
        await self._repo.create(record)
        await self._queue.put(job_id)
        logger.info("Created job %s (file: %s)", job_id, input_filename)
        return record

    async def get_job(self, job_id: str) -> JobRecord | None:
        return await self._repo.get(job_id)

    async def list_jobs(self, limit: int = 20, offset: int = 0) -> list[JobRecord]:
        return await self._repo.list(type_filter="sbom_enrich", limit=limit, offset=offset)

    async def cancel_job(self, job_id: str) -> bool:
        record = await self._repo.get(job_id)
        if not record or record.status in ("completed", "failed", "cancelled"):
            return False
        await self._repo.update_status(job_id, "cancelled", cancel_requested=1, finished_at=_now())
        task = self._running_tasks.get(job_id)
        if task is not None and not task.done():
            task.cancel()
        return True

    async def delete_job(self, job_id: str) -> bool:
        record = await self._repo.get(job_id)
        if not record:
            return False
        job_dir = JOBS_DIR / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
        await self._repo.delete(job_id)
        return True

    async def _run_worker(self) -> None:
        while True:
            job_id = await self._queue.get()
            task = asyncio.create_task(self._process_job(job_id))
            self._running_tasks[job_id] = task
            try:
                await task
            except asyncio.CancelledError:
                logger.info("Job %s processing cancelled, discarding result", job_id)
                job_dir = JOBS_DIR / job_id
                if job_dir.exists():
                    shutil.rmtree(job_dir)
            except Exception:
                logger.exception("Unhandled error processing job %s", job_id)
            finally:
                self._running_tasks.pop(job_id, None)
                self._queue.task_done()

    async def _process_job(self, job_id: str) -> None:
        record = await self._repo.get(job_id)
        if not record:
            return

        if record.status in ("cancelled",):
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir)
            return

        if record.cancel_requested:
            await self._repo.update_status(job_id, "cancelled", finished_at=_now())
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir)
            return

        await self._repo.update_status(job_id, "running", started_at=_now())

        record = await self._repo.get(job_id)
        if record and record.cancel_requested:
            await self._repo.update_status(job_id, "cancelled", finished_at=_now())
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                shutil.rmtree(job_dir)
            return

        try:
            input_path = JOBS_DIR / job_id / "input.json"
            sbom_data = json.loads(input_path.read_text())

            params = record.get_params()
            remove_unresolved = params.get("remove_unresolved_no_subcomponents", False)
            ignore_patterns = params.get("ignore_patterns")

            pipeline = SbomEnrichmentPipeline(self._resolution_service)
            reporter = _JobProgressReporter(self._repo, job_id)

            result = await pipeline.process(
                sbom_data,
                remove_unresolved_no_subcomponents=remove_unresolved,
                ignore_patterns=ignore_patterns,
                progress_reporter=reporter,
            )

            record = await self._repo.get(job_id)
            if record and (record.status == "cancelled" or record.cancel_requested):
                return

            result_path = JOBS_DIR / job_id / "result.json"
            result_path.write_text(json.dumps(result.enriched_sbom, indent=2))

            await self._repo.update_status(
                job_id,
                "completed",
                result_path=str(result_path),
                summary_json=json.dumps(result.report["summary"]),
                results_json=json.dumps(result.report.get("results", [])),
                finished_at=_now(),
            )

        except SbomParseError as e:
            await self._repo.update_status(
                job_id,
                "failed",
                error_message=f"Invalid SBOM: {e}",
                finished_at=_now(),
            )
        except Exception as e:
            await self._repo.update_status(
                job_id,
                "failed",
                error_message=str(e),
                finished_at=_now(),
            )

    async def _run_cleanup(self) -> None:
        while True:
            await asyncio.sleep(60)
            try:
                expired = await self._repo.get_expired(self._job_ttl_hours)
                for job in expired:
                    job_dir = JOBS_DIR / job.id
                    if job_dir.exists():
                        shutil.rmtree(job_dir)
                    await self._repo.delete(job.id)
                    logger.info("Cleaned up expired job %s", job.id)
            except Exception:
                logger.exception("Error during job cleanup")
