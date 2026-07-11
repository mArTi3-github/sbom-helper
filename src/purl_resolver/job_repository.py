from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import asyncpg


@dataclass
class JobRecord:
    id: str
    type: str
    status: str
    progress_current: int = 0
    progress_total: int = 0
    params_json: str | None = None
    input_filename: str | None = None
    result_path: str | None = None
    summary_json: str | None = None
    results_json: str | None = None
    error_message: str | None = None
    cancel_requested: int = 0
    created_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None

    def get_params(self) -> dict[str, Any]:
        return json.loads(self.params_json) if self.params_json else {}

    def get_summary(self) -> dict[str, Any] | None:
        return json.loads(self.summary_json) if self.summary_json else None

    def get_results(self) -> list[dict[str, Any]] | None:
        return json.loads(self.results_json) if self.results_json else None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


_COLUMNS = (
    "id",
    "type",
    "status",
    "progress_current",
    "progress_total",
    "params_json",
    "input_filename",
    "result_path",
    "summary_json",
    "results_json",
    "error_message",
    "cancel_requested",
    "created_at",
    "started_at",
    "finished_at",
)


class JobRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, record: JobRecord) -> None:
        record.created_at = _now()
        async with self._pool.acquire() as conn:
            await conn.execute(
                f"INSERT INTO jobs ({', '.join(_COLUMNS)}) "
                f"VALUES ({', '.join(f'${i + 1}' for i in range(len(_COLUMNS)))})",
                *[getattr(record, c) for c in _COLUMNS],
            )

    async def get(self, job_id: str) -> JobRecord | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM jobs WHERE id = $1", job_id)
        return self._row_to_record(row) if row else None

    async def list(
        self,
        type_filter: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[JobRecord]:
        if type_filter:
            query = "SELECT * FROM jobs WHERE type = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"
            params = [type_filter, limit, offset]
        else:
            query = "SELECT * FROM jobs ORDER BY created_at DESC LIMIT $1 OFFSET $2"
            params = [limit, offset]
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
        return [self._row_to_record(r) for r in rows]

    async def update_status(
        self,
        job_id: str,
        status: str,
        **fields: Any,
    ) -> None:
        set_parts = ["status = $1"]
        values: list[Any] = [status]
        i = 2
        for key, val in fields.items():
            set_parts.append(f"{key} = ${i}")
            values.append(val)
            i += 1
        values.append(job_id)
        async with self._pool.acquire() as conn:
            await conn.execute(f"UPDATE jobs SET {', '.join(set_parts)} WHERE id = ${i}", *values)

    async def delete(self, job_id: str) -> bool:
        async with self._pool.acquire() as conn:
            result = await conn.execute("DELETE FROM jobs WHERE id = $1", job_id)
        return result != "DELETE 0"

    async def get_queued(self) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status = 'queued' ORDER BY created_at ASC"
            )
        return [self._row_to_record(r) for r in rows]

    async def get_stuck_running(self) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM jobs WHERE status = 'running'")
        return [self._row_to_record(r) for r in rows]

    async def get_expired(self, ttl_hours: int) -> list[JobRecord]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM jobs WHERE status IN ('completed','failed','cancelled') "
                "AND finished_at IS NOT NULL "
                "AND finished_at::timestamptz < NOW() - make_interval(hours => $1)",
                ttl_hours,
            )
        return [self._row_to_record(r) for r in rows]

    @staticmethod
    def _row_to_record(row: asyncpg.Record) -> JobRecord:
        return JobRecord(**{k: row[k] for k in _COLUMNS})
