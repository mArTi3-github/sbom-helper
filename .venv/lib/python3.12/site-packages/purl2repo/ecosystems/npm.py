"""npm registry adapter."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like
from purl2repo.utils.urls import is_repo_like_url


class NpmResolver(EcosystemResolver):
    ecosystem = "npm"
    metadata_source = "npm-registry"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        package_name = npm_package_name(parsed)
        encoded = quote(package_name, safe="")
        return client.get_json(f"https://registry.npmjs.org/{encoded}")

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        candidates: list[RepositoryCandidate | None] = []

        version_metadata = self._version_metadata(parsed, metadata)
        candidates.extend(_repository_candidates(version_metadata.get("repository")))
        candidates.extend(_repository_candidates(metadata.get("repository")))

        for homepage in (version_metadata.get("homepage"), metadata.get("homepage")):
            if (
                isinstance(homepage, str)
                and not is_docs_like(homepage)
                and is_repo_like_url(homepage)
            ):
                candidates.append(
                    make_candidate(homepage, "homepage", "Homepage points to repo root")
                )

        return dedupe_candidates(candidates)

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        package_name = npm_package_name(parsed)
        pages = [f"https://www.npmjs.com/package/{package_name}"]
        homepage = metadata.get("homepage")
        if isinstance(homepage, str):
            pages.append(homepage)
        repository = metadata.get("repository")
        if isinstance(repository, dict):
            url = repository.get("url")
            if isinstance(url, str):
                pages.append(url)
        return pages

    def _version_metadata(self, parsed: ParsedPurl, metadata: Metadata) -> Metadata:
        if not parsed.version:
            return {}
        versions = metadata.get("versions")
        if isinstance(versions, dict):
            version_data = versions.get(parsed.version)
            if isinstance(version_data, dict):
                return version_data
        return {}


def npm_package_name(parsed: ParsedPurl) -> str:
    return f"{parsed.namespace}/{parsed.name}" if parsed.namespace else parsed.name


def _repository_candidates(repository: Any) -> list[RepositoryCandidate | None]:
    if isinstance(repository, str):
        return [
            make_candidate(
                repository,
                "repository_field",
                "Candidate from npm repository field",
            )
        ]
    if isinstance(repository, dict):
        url = repository.get("url")
        if isinstance(url, str):
            return [
                make_candidate(
                    url,
                    "repository_field",
                    "Candidate from npm repository.url field",
                )
            ]
    return []
