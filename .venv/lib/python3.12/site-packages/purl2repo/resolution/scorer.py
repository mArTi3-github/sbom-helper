"""Transparent repository candidate scoring."""

from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

from purl2repo.models import ParsedPurl, RepositoryCandidate
from purl2repo.utils.text import is_docs_like, is_issue_like, package_name_tokens
from purl2repo.utils.urls import classify_host, normalize_repo_url

SOURCE_WEIGHTS = {
    "project_urls_source": 95.0,
    "project_urls_repository": 95.0,
    "project_urls_code": 95.0,
    "repository_field": 100.0,
    "registry_api": 100.0,
    "pom_scm": 100.0,
    "pom_parent_scm": 55.0,
    "homepage": 85.0,
    "metadata_page": 45.0,
    "module_path": 95.0,
    "go_import_meta": 100.0,
    "deps_dev_related_project": 55.0,
    "deps_dev_link": 50.0,
    "deps_dev_attestation": 60.0,
    "scrape": 35.0,
    "user_override": 100.0,
}

SOURCE_PRIORITY = {
    "repository_field": 0,
    "registry_api": 1,
    "pom_scm": 1,
    "pom_parent_scm": 4,
    "project_urls_source": 2,
    "project_urls_repository": 2,
    "project_urls_code": 2,
    "homepage": 3,
    "metadata_page": 4,
    "module_path": 2,
    "go_import_meta": 1,
    "deps_dev_attestation": 4,
    "deps_dev_related_project": 4,
    "deps_dev_link": 4,
    "scrape": 5,
    "user_override": 0,
}


def confidence_from_score(score: float) -> str:
    if score >= 90:
        return "high"
    if score >= 65:
        return "medium"
    if score >= 35:
        return "low"
    return "none"


def _package_name_matches_path(parsed: ParsedPurl, normalized_url: str) -> bool:
    tokens = package_name_tokens(parsed.name)
    if not tokens:
        return False
    path = urlsplit(normalized_url).path.lower()
    joined = parsed.name.lower().replace("_", "-")
    return joined in path or any(token in path for token in tokens)


GENERIC_MODULE_TOKENS = {
    "api",
    "annotations",
    "client",
    "common",
    "commons",
    "core",
    "ext",
    "extension",
    "extensions",
    "framework",
    "impl",
    "java",
    "javax",
    "module",
    "parent",
    "project",
    "server",
    "service",
    "services",
    "support",
    "test",
    "testing",
    "util",
    "utils",
}


def _scraped_candidate_matches_package(parsed: ParsedPurl, normalized_url: str) -> bool:
    path = urlsplit(normalized_url).path.lower()
    joined = parsed.name.lower().replace("_", "-")
    if joined in path:
        return True
    tokens = [
        token for token in package_name_tokens(parsed.name) if token not in GENERIC_MODULE_TOKENS
    ]
    if not tokens:
        return _package_name_matches_path(parsed, normalized_url)
    return all(token in path for token in tokens)


def score_candidate(candidate: RepositoryCandidate, parsed: ParsedPurl) -> RepositoryCandidate:
    score = SOURCE_WEIGHTS.get(candidate.source, 25.0)
    reasons = list(candidate.reasons)

    normalized = normalize_repo_url(candidate.normalized_url or candidate.url)
    if normalized:
        if normalized != candidate.url:
            reasons.append("Normalized to canonical repo root")
        score += 10
    else:
        normalized = candidate.url
        score -= 100
        reasons.append("Malformed or unresolvable repository URL")

    host = urlsplit(normalized).hostname or ""
    repository_type = classify_host(host)
    if repository_type != "generic_git":
        score += 10
        reasons.append(f"Recognized {repository_type} hosting provider")

    if _package_name_matches_path(parsed, normalized):
        score += 5
        reasons.append("Package name appears in repository path")

    original_lower = candidate.url.lower()
    if is_docs_like(original_lower):
        score -= 25
        reasons.append("URL appears to point to documentation rather than source")
    if is_issue_like(original_lower) and normalized == candidate.url.rstrip("/"):
        score -= 15
        reasons.append("URL appears to point to an issue tracker")

    path_segments = [segment for segment in urlsplit(normalized).path.split("/") if segment]
    if repository_type in {"github", "bitbucket"} and len(path_segments) < 2:
        score -= 40
        reasons.append("URL points to an organization root, not a repository")

    if candidate.source == "scrape":
        if _scraped_candidate_matches_package(parsed, normalized):
            score = min(score, 60.0)
            reasons.append("Scraped candidate score capped below structured metadata")
        else:
            score = min(score, 34.0)
            reasons.append(
                "Scraped candidate path does not match package name; "
                "capped below confidence threshold"
            )
    if candidate.source.startswith("deps_dev_"):
        score = min(score, 75.0)
        reasons.append("deps.dev candidate score capped below first-party metadata")
    if candidate.source == "pom_parent_scm":
        score = min(score, 74.0)
        reasons.append("Inherited Maven parent SCM candidate capped below high confidence")

    return replace(
        candidate,
        normalized_url=normalized,
        host=host,
        repository_type=repository_type,
        score=max(score, 0.0),
        reasons=reasons,
    )


def sort_candidates(candidates: list[RepositoryCandidate]) -> list[RepositoryCandidate]:
    return sorted(
        candidates,
        key=lambda candidate: (
            -candidate.score,
            SOURCE_PRIORITY.get(candidate.source, 99),
            candidate.normalized_url,
        ),
    )


def score_candidates(
    candidates: list[RepositoryCandidate], parsed: ParsedPurl
) -> list[RepositoryCandidate]:
    return sort_candidates([score_candidate(candidate, parsed) for candidate in candidates])
