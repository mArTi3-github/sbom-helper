"""PyPI registry adapter."""

from __future__ import annotations

from typing import Any

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.errors import MetadataFetchError
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like, is_source_label, normalize_label
from purl2repo.utils.urls import is_repo_like_url


class PyPiResolver(EcosystemResolver):
    ecosystem = "pypi"
    metadata_source = "pypi-json"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        if parsed.version:
            url = f"https://pypi.org/pypi/{parsed.name}/{parsed.version}/json"
            try:
                return client.get_json(url)
            except MetadataFetchError:
                project_metadata = client.get_json(f"https://pypi.org/pypi/{parsed.name}/json")
                project_metadata["_purl2repo_version_metadata_missing"] = parsed.version
                return project_metadata
        return client.get_json(f"https://pypi.org/pypi/{parsed.name}/json")

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        _ = parsed
        info = metadata.get("info", {})
        if not isinstance(info, dict):
            info = {}
        candidates: list[RepositoryCandidate | None] = []

        project_urls = info.get("project_urls") or {}
        if isinstance(project_urls, dict):
            for label, url in project_urls.items():
                if not isinstance(label, str) or not isinstance(url, str):
                    continue
                if is_source_label(label):
                    source = f"project_urls_{label.lower().replace(' ', '_')}"
                    if source not in {
                        "project_urls_source",
                        "project_urls_repository",
                        "project_urls_code",
                    }:
                        source = "project_urls_source"
                    candidates.append(
                        make_candidate(url, source, f"Candidate from project_urls['{label}']")
                    )
                elif (
                    not _is_non_repository_label(label)
                    and not is_docs_like(f"{label} {url}")
                    and is_repo_like_url(url)
                ):
                    candidates.append(
                        make_candidate(
                            url,
                            "project_urls_source",
                            f"Repo-like project URL: {label}",
                        )
                    )

        home_page = _string_value(info.get("home_page"))
        if home_page and not is_docs_like(home_page) and is_repo_like_url(home_page):
            candidates.append(make_candidate(home_page, "homepage", "Homepage points to repo root"))

        download_url = _string_value(info.get("download_url"))
        if download_url and not is_docs_like(download_url) and is_repo_like_url(download_url):
            candidates.append(
                make_candidate(
                    download_url,
                    "metadata_page",
                    "Download URL points to repo-like page",
                )
            )

        return dedupe_candidates(candidates)

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        pages = [f"https://pypi.org/project/{parsed.name}/"]
        info = metadata.get("info")
        if isinstance(info, dict):
            pages.extend(_metadata_urls(info))
        return pages


def _string_value(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() else None


def _is_non_repository_label(label: str) -> bool:
    normalized = normalize_label(label)
    return any(
        word in normalized.split()
        for word in {"donate", "donation", "funding", "sponsor", "support"}
    )


def _metadata_urls(info: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("home_page", "download_url"):
        value = _string_value(info.get(key))
        if value:
            urls.append(value)
    project_urls = info.get("project_urls")
    if isinstance(project_urls, dict):
        for value in project_urls.values():
            if isinstance(value, str):
                urls.append(value)
    return urls
