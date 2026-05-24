"""Third-party fallback metadata from deps.dev."""

from __future__ import annotations

from urllib.parse import quote

from purl2repo.ecosystems.base import Metadata, dedupe_candidates, make_candidate
from purl2repo.errors import MetadataFetchError
from purl2repo.http.client import HttpClient
from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like, is_source_label
from purl2repo.utils.urls import is_repo_like_url

DEPS_DEV_SYSTEMS = {
    "cargo": "CARGO",
    "golang": "GO",
    "maven": "MAVEN",
    "npm": "NPM",
    "nuget": "NUGET",
    "pypi": "PYPI",
}


def fetch_deps_dev_candidates(
    parsed: ParsedPurl,
    client: HttpClient,
) -> tuple[list[RepositoryCandidate], list[str], list[str]]:
    """Return repository candidates from deps.dev as a conservative fallback."""

    system = DEPS_DEV_SYSTEMS.get(parsed.type)
    if system is None:
        return [], [], []

    package_name = _deps_dev_package_name(parsed)
    package_url = _package_url(system, package_name)
    evidence = ["Queried deps.dev as a third-party fallback metadata source"]
    warnings: list[str] = []
    payload: Metadata | None = None

    if parsed.version:
        try:
            payload = client.get_json(_version_url(system, package_name, parsed.version))
        except MetadataFetchError as exc:
            warnings.append(f"deps.dev version lookup failed: {exc}")

    if payload is None:
        try:
            package = client.get_json(package_url)
        except MetadataFetchError as exc:
            warnings.append(f"deps.dev package lookup failed: {exc}")
            return [], evidence, warnings
        default_version = _default_version(package)
        if default_version:
            evidence.append(
                f"Used deps.dev default version {default_version} for repository fallback"
            )
            try:
                payload = client.get_json(_version_url(system, package_name, default_version))
            except MetadataFetchError as exc:
                warnings.append(f"deps.dev default version lookup failed: {exc}")
                return [], evidence, warnings
        else:
            return [], evidence, warnings

    return _extract_candidates(payload), evidence, warnings


def _deps_dev_package_name(parsed: ParsedPurl) -> str:
    if parsed.type == "maven" and parsed.namespace:
        return f"{parsed.namespace}:{parsed.name}"
    if parsed.type == "npm" and parsed.namespace:
        return f"{parsed.namespace}/{parsed.name}"
    if parsed.type == "golang" and parsed.namespace:
        return f"{parsed.namespace}/{parsed.name}"
    return parsed.name


def _package_url(system: str, package_name: str) -> str:
    return f"https://api.deps.dev/v3/systems/{system}/packages/{quote(package_name, safe='')}"


def _version_url(system: str, package_name: str, version: str) -> str:
    return f"{_package_url(system, package_name)}/versions/{quote(version, safe='')}"


def _default_version(package: Metadata) -> str | None:
    versions = package.get("versions")
    if not isinstance(versions, list):
        return None
    for version in versions:
        if not isinstance(version, dict) or not version.get("isDefault"):
            continue
        version_key = version.get("versionKey")
        if isinstance(version_key, dict):
            version_value = version_key.get("version")
            if isinstance(version_value, str):
                return version_value
    return None


def _extract_candidates(payload: Metadata) -> list[RepositoryCandidate]:
    candidates: list[RepositoryCandidate | None] = []

    for project in _dict_items(payload.get("relatedProjects")):
        if project.get("relationType") != "SOURCE_REPO":
            continue
        project_key = project.get("projectKey")
        if not isinstance(project_key, dict):
            continue
        project_id = project_key.get("id")
        if isinstance(project_id, str) and project_id:
            candidates.append(
                make_candidate(
                    f"https://{project_id}",
                    "deps_dev_related_project",
                    "Candidate from deps.dev relatedProjects SOURCE_REPO",
                )
            )

    for link in _dict_items(payload.get("links")):
        label = str(link.get("label", ""))
        url = link.get("url")
        if not isinstance(url, str):
            continue
        normalized_label = label.replace("_", " ").lower()
        if is_source_label(normalized_label):
            candidates.append(
                make_candidate(
                    url,
                    "deps_dev_link",
                    f"Candidate from deps.dev link labeled {label}",
                )
            )
        elif normalized_label == "homepage" and is_repo_like_url(url) and not is_docs_like(url):
            candidates.append(
                make_candidate(
                    url,
                    "deps_dev_link",
                    "Candidate from deps.dev homepage link that looks repository-like",
                )
            )

    for provenance in _dict_items(payload.get("slsaProvenances")):
        source_repository = provenance.get("sourceRepository")
        if isinstance(source_repository, str) and source_repository:
            candidates.append(
                make_candidate(
                    source_repository,
                    "deps_dev_attestation",
                    "Candidate from deps.dev SLSA provenance sourceRepository",
                )
            )

    for attestation in _dict_items(payload.get("attestations")):
        source_repository = attestation.get("sourceRepository")
        if isinstance(source_repository, str) and source_repository:
            candidates.append(
                make_candidate(
                    source_repository,
                    "deps_dev_attestation",
                    "Candidate from deps.dev attestation sourceRepository",
                )
            )

    return dedupe_candidates(candidates)


def _dict_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
