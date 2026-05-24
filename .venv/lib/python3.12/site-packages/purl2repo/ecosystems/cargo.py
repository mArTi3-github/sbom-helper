"""Cargo crates.io adapter."""

from __future__ import annotations

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like
from purl2repo.utils.urls import is_repo_like_url


class CargoResolver(EcosystemResolver):
    ecosystem = "cargo"
    metadata_source = "crates.io"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        return client.get_json(f"https://crates.io/api/v1/crates/{parsed.name}")

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        _ = parsed
        crate = metadata.get("crate")
        if not isinstance(crate, dict):
            crate = {}
        candidates: list[RepositoryCandidate | None] = []
        repository = crate.get("repository")
        if isinstance(repository, str):
            candidates.append(
                make_candidate(
                    repository,
                    "repository_field",
                    "Candidate from crates.io repository field",
                )
            )
        homepage = crate.get("homepage")
        if isinstance(homepage, str) and not is_docs_like(homepage) and is_repo_like_url(homepage):
            candidates.append(make_candidate(homepage, "homepage", "Homepage points to repo root"))
        return dedupe_candidates(candidates)

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        pages = [f"https://crates.io/crates/{parsed.name}"]
        crate = metadata.get("crate")
        if isinstance(crate, dict):
            homepage = crate.get("homepage")
            if isinstance(homepage, str):
                pages.append(homepage)
        return pages
