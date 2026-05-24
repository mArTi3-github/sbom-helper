"""NuGet registry adapter."""

from __future__ import annotations

from typing import Any

from purl2repo.ecosystems.base import EcosystemResolver, Metadata, dedupe_candidates, make_candidate
from purl2repo.hosts.base import HostAdapter
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, ReleaseLink, RepositoryCandidate
from purl2repo.utils.text import is_docs_like
from purl2repo.utils.urls import is_repo_like_url


class NuGetResolver(EcosystemResolver):
    ecosystem = "nuget"
    metadata_source = "nuget-registration"

    def fetch_metadata(self, parsed: ParsedPurl, client: HttpClient) -> Metadata:
        package = parsed.name.lower()
        url = f"https://api.nuget.org/v3/registration5-semver1/{package}/index.json"
        metadata = client.get_json(url)
        metadata["package_id"] = parsed.name
        return metadata

    def extract_candidates(
        self, parsed: ParsedPurl, metadata: Metadata
    ) -> list[RepositoryCandidate]:
        _ = parsed
        candidates: list[RepositoryCandidate | None] = []
        for entry in _catalog_entries(metadata):
            repository = entry.get("repository")
            if isinstance(repository, dict):
                url = repository.get("url")
                if isinstance(url, str):
                    candidates.append(
                        make_candidate(
                            url,
                            "repository_field",
                            "Candidate from NuGet catalogEntry.repository.url field",
                        )
                    )
            repository_url = entry.get("repositoryUrl")
            if isinstance(repository_url, str):
                candidates.append(
                    make_candidate(
                        repository_url,
                        "repository_field",
                        "Candidate from NuGet catalogEntry.repositoryUrl field",
                    )
                )
            project_url = entry.get("projectUrl")
            if (
                isinstance(project_url, str)
                and not is_docs_like(project_url)
                and is_repo_like_url(project_url)
            ):
                candidates.append(
                    make_candidate(
                        project_url,
                        "homepage",
                        "NuGet projectUrl points to repo root",
                    )
                )
        return dedupe_candidates(candidates)

    def resolve_release_link(
        self,
        parsed: ParsedPurl,
        repository: RepositoryCandidate | None,
        metadata: Metadata,
        host_adapter: HostAdapter | None,
    ) -> ReleaseLink | None:
        _ = repository, metadata, host_adapter
        if not parsed.version:
            return None
        return ReleaseLink(
            url=f"https://www.nuget.org/packages/{parsed.name}/{parsed.version}",
            kind="package",
            version=parsed.version,
            source="nuget",
        )

    def fallback_scrape_pages(self, parsed: ParsedPurl, metadata: Metadata) -> list[str]:
        pages = [f"https://www.nuget.org/packages/{parsed.name}"]
        for entry in _catalog_entries(metadata):
            project_url = entry.get("projectUrl")
            if isinstance(project_url, str):
                pages.append(project_url)
        return pages


def _catalog_entries(metadata: Metadata) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in metadata.get("items", []):
        if not isinstance(item, dict):
            continue
        catalog_entry = item.get("catalogEntry")
        if isinstance(catalog_entry, dict):
            entries.append(catalog_entry)
        for child in item.get("items", []):
            if not isinstance(child, dict):
                continue
            child_entry = child.get("catalogEntry")
            if isinstance(child_entry, dict):
                entries.append(child_entry)
    if isinstance(metadata.get("catalogEntry"), dict):
        entries.append(metadata["catalogEntry"])
    return entries
