from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
from pathlib import Path

from .job_repository import JobRecord, JobRepository, _new_id, _now
from .sbom_enrichment import SbomEnrichmentPipeline
from .sbom.parser import SbomParseError
from .service import PurlResolutionService

logger = logging.getLogger(__name__)

JOBS_DIR = Path(os.environ.get("JOBS_DIR", "data/jobs"))


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
        self._worker_task: asyncio.Task | None = None
        self._cleanup_task: asyncio.Task | None = None

    async def start(self) -> None:
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

        stuck = await self._repo.get_stuck_running()
        for job in stuck:
            await self._repo.update_status(
                job.id, "failed",
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
        await self._repo.update_status(job_id, record.status, cancel_requested=1)
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
            try:
                await self._process_job(job_id)
            except Exception:
                logger.exception("Unhandled error processing job %s", job_id)
            finally:
                self._queue.task_done()

    async def _process_job(self, job_id: str) -> None:
        record = await self._repo.get(job_id)
        if not record:
            return

        if record.cancel_requested:
            await self._repo.update_status(
                job_id, "cancelled", finished_at=_now()
            )
            job_dir = JOBS_DIR / job_id
            if job_dir.exists():
                import shutil
                shutil.rmtree(job_dir)
            return

        await self._repo.update_status(
            job_id, "running", started_at=_now()
        )

        try:
            input_path = JOBS_DIR / job_id / "input.json"
            sbom_data = json.loads(input_path.read_text())

            params = record.get_params()
            remove_unresolved = params.get("remove_unresolved_no_subcomponents", False)
            ignore_patterns = params.get("ignore_patterns")

            pipeline = SbomEnrichmentPipeline(self._resolution_service)

            result = await pipeline.process(
                sbom_data,
                remove_unresolved_no_subcomponents=remove_unresolved,
                ignore_patterns=ignore_patterns,
            )

            result_path = JOBS_DIR / job_id / "result.json"
            result_path.write_text(
                json.dumps(result.enriched_sbom, indent=2)
            )

            await self._repo.update_status(
                job_id, "completed",
                result_path=str(result_path),
                summary_json=json.dumps(result.report),
                results_json=json.dumps(result.report.get("results", [])),
                finished_at=_now(),
            )

        except SbomParseError as e:
            await self._repo.update_status(
                job_id, "failed",
                error_message=f"Invalid SBOM: {e}",
                finished_at=_now(),
            )
        except Exception as e:
            await self._repo.update_status(
                job_id, "failed",
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
                        import shutil
                        shutil.rmtree(job_dir)
                    await self._repo.delete(job.id)
                    logger.info("Cleaned up expired job %s", job.id)
            except Exception:
                logger.exception("Error during job cleanup")
