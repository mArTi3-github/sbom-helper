from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from ..schemas import BatchResolveItem, BatchResolveRequest, BatchResolveResponse
from ..settings_store import SettingsStore
from ..source_archive.service import SourceArchiveResult
from ..url_validator import ensure_connectivity

router = APIRouter()
logger = logging.getLogger(__name__)

_COMMIT_SHA = re.compile(r"^[0-9a-f]{40}$")


def _commit_sha_from_url(url: str | None) -> str | None:
    if url is None:
        return None
    try:
        name = urlsplit(url).path.rsplit("/", 1)[-1]
    except ValueError:
        return None
    if name.endswith(".tar.gz"):
        name = name[: -len(".tar.gz")]
    return name if _COMMIT_SHA.fullmatch(name) else None


@router.post("/api/v1/resolve/batch")
async def resolve_batch_endpoint(body: BatchResolveRequest, request: Request) -> JSONResponse:
    try:
        settings: SettingsStore = request.app.state.settings_store
        app_settings = settings.load()
        await ensure_connectivity(
            url=app_settings.connectivity_url,
            timeout=app_settings.connectivity_timeout,
        )
    except ConnectionError:
        return JSONResponse(
            status_code=503,
            content={"error": "network_unavailable"},
        )

    if len(body.purls) > app_settings.batch_max_items:
        return JSONResponse(
            status_code=400,
            content={
                "error": "batch_too_large",
                "detail": f"Maximum {app_settings.batch_max_items} PURLs per request",
            },
        )

    results = await request.app.state.resolution_service.resolve_many(purls=body.purls)

    items: list[BatchResolveItem] = []
    archive_indices: list[int] = []
    archive_purls: list[str] = []
    archive_repository_urls: list[str | None] = []
    for original, result in zip(body.purls, results):
        if result.error_status is not None:
            items.append(
                BatchResolveItem(
                    purl=original,
                    error=result.error_body.get("error") if result.error_body else "error",
                )
            )
        elif result.response is not None:
            response_data = result.response.model_dump()
            response_data["purl"] = original
            items.append(BatchResolveItem(**response_data))
            if body.find_source_archive:
                archive_indices.append(len(items) - 1)
                archive_purls.append(original)
                archive_repository_urls.append(result.response.repository_url)

    if body.find_source_archive and archive_purls:
        try:
            archive_results = await request.app.state.source_archive_service.enrich_many(
                purls=archive_purls,
                repository_urls=archive_repository_urls,
                force_refresh=body.force_refresh,
            )
        except Exception:
            logger.warning(
                "Source archive enrichment failed for the batch", exc_info=True
            )
            archive_results = [
                SourceArchiveResult(
                    purl=purl,
                    match_type="repository_only" if repository_url else "not_found",
                    reason="internal_error",
                    repository_url=repository_url,
                    resolved_at=datetime.now(timezone.utc).isoformat(),
                )
                for purl, repository_url in zip(
                    archive_purls, archive_repository_urls
                )
            ]
        for index, archive_result in zip(archive_indices, archive_results):
            item = items[index]
            item.source_archive_url = archive_result.archive_url
            item.source_archive_commit_url = archive_result.archive_url_commit
            item.source_archive_commit_sha = _commit_sha_from_url(
                archive_result.archive_url_commit
            )
            item.source_archive_match = archive_result.match_type
            item.source_archive_reason = archive_result.reason
            item.source_archive_ref = archive_result.matched_ref
            item.source_archive_ref_type = archive_result.matched_ref_type
            item.source_archive_matched_version = archive_result.matched_version
            item.source_archive_resolver = archive_result.resolver
            item.source_archive_cached = archive_result.cached
            item.source_archive_resolved_at = archive_result.resolved_at
            item.warnings = [*item.warnings, *archive_result.warnings]

    return JSONResponse(
        status_code=200,
        content=BatchResolveResponse(results=items).model_dump(),
    )
