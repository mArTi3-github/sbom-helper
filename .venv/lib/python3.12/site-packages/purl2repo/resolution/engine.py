"""Resolution pipeline orchestration."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from urllib.parse import urlsplit, urlunsplit

from purl2repo.ecosystems.base import EcosystemResolver, Metadata
from purl2repo.ecosystems.cargo import CargoResolver
from purl2repo.ecosystems.golang import GoResolver
from purl2repo.ecosystems.maven import MavenResolver
from purl2repo.ecosystems.npm import NpmResolver
from purl2repo.ecosystems.nuget import NuGetResolver
from purl2repo.ecosystems.pypi import PyPiResolver
from purl2repo.errors import (
    MetadataFetchError,
    NoReleaseFoundError,
    NoRepositoryFoundError,
    UnsupportedEcosystemError,
)
from purl2repo.hosts.base import HostAdapter
from purl2repo.hosts.bitbucket import BitbucketAdapter
from purl2repo.hosts.generic_git import GenericGitAdapter
from purl2repo.hosts.github import GitHubAdapter
from purl2repo.hosts.gitlab import GitLabAdapter
from purl2repo.http.client import HttpClient
from purl2repo.models import (
    ParsedPurl,
    ReleaseLink,
    RepositoryCandidate,
    RepositoryRef,
    ResolutionResult,
    ResolverSettings,
)
from purl2repo.purl.parse import parse_purl
from purl2repo.resolution import evidence as evidence_messages
from purl2repo.resolution.cache import ResponseCache
from purl2repo.resolution.deps_dev import fetch_deps_dev_candidates
from purl2repo.resolution.scorer import confidence_from_score, score_candidates
from purl2repo.resolution.scraper import (
    FallbackScraper,
    default_fallback_pages,
    scraped_to_repository_candidate,
    should_scrape_purl,
)
from purl2repo.utils.urls import classify_host, coerce_git_url, normalize_repo_url, url_host

ECOSYSTEMS: dict[str, type[EcosystemResolver]] = {
    "cargo": CargoResolver,
    "golang": GoResolver,
    "maven": MavenResolver,
    "npm": NpmResolver,
    "nuget": NuGetResolver,
    "pypi": PyPiResolver,
}

DIRECT_HOST_TYPES = {"github", "bitbucket"}
ARTIFACT_HUB_TYPES = {"huggingface", "mlflow"}
GENERIC_TYPES = {"generic"}
SUPPORTED_PURL_TYPES = set(ECOSYSTEMS) | DIRECT_HOST_TYPES | ARTIFACT_HUB_TYPES | GENERIC_TYPES

HOSTS: dict[str, HostAdapter] = {
    "github.com": GitHubAdapter(),
    "gitlab.com": GitLabAdapter(),
    "bitbucket.org": BitbucketAdapter(),
}
GENERIC_HOST = GenericGitAdapter()


class ResolutionEngine:
    def __init__(self, settings: ResolverSettings) -> None:
        self.settings = settings
        self.cache = ResponseCache(settings.cache_dir) if settings.use_cache else None
        self.client = HttpClient(settings, self.cache)
        self.scraper = FallbackScraper(self.client)

    def close(self) -> None:
        self.client.close()

    def parse(self, purl: str) -> ParsedPurl:
        return parse_purl(purl)

    def resolve(self, purl: str, *, include_release: bool = True) -> ResolutionResult:
        parsed = self.parse(purl)
        if parsed.type in DIRECT_HOST_TYPES:
            return self._resolve_direct_host(parsed, include_release=include_release)
        if parsed.type in ARTIFACT_HUB_TYPES:
            return self._resolve_artifact_hub(parsed, include_release=include_release)
        if parsed.type in GENERIC_TYPES:
            return self._resolve_generic(parsed, include_release=include_release)

        adapter = self._adapter_for(parsed)
        warnings: list[str] = []
        evidence: list[str] = []
        metadata_sources = [adapter.metadata_source]
        metadata: Metadata = {}

        try:
            metadata = adapter.fetch_metadata(parsed, self.client)
            evidence.append(evidence_messages.fetched(adapter.metadata_source))
            metadata_warning = metadata.get("_purl2repo_metadata_warning")
            if isinstance(metadata_warning, str):
                warnings.append(metadata_warning)
            missing_version = metadata.get("_purl2repo_version_metadata_missing")
            if isinstance(missing_version, str):
                warnings.append(
                    "Version-specific metadata was not found; "
                    f"used project metadata for {missing_version}"
                )
                evidence.append(
                    "Used project-level metadata after version-specific metadata failed"
                )
        except MetadataFetchError as exc:
            if self.settings.strict:
                raise
            warnings.append(f"Could not fetch metadata from {adapter.metadata_source}")
            fallback_metadata = adapter.metadata_fetch_fallback(parsed)
            if fallback_metadata is None and self.settings.no_network:
                return self._empty_result(parsed, warnings, evidence, metadata_sources)
            metadata = fallback_metadata or {}
            if fallback_metadata is not None:
                evidence.append(
                    f"Used resolver-local fallback metadata after {adapter.metadata_source} failed"
                )
            warnings.append(f"Continuing after metadata fetch failure: {exc}")

        candidates = self._validate_repository_candidates(
            score_candidates(adapter.extract_candidates(parsed, metadata), parsed),
            warnings,
            evidence,
        )
        structured_confidence = confidence_from_score(candidates[0].score if candidates else 0.0)
        if (
            structured_confidence == "none"
            and not self.settings.no_network
            and self.settings.use_deps_dev_fallback
        ):
            deps_candidates, deps_evidence, deps_warnings = fetch_deps_dev_candidates(
                parsed,
                self.client,
            )
            evidence.extend(deps_evidence)
            warnings.extend(deps_warnings)
            if deps_evidence:
                metadata_sources.append("deps-dev")
            if deps_candidates:
                candidates = self._validate_repository_candidates(
                    score_candidates([*candidates, *deps_candidates], parsed),
                    warnings,
                    evidence,
                )
                structured_confidence = confidence_from_score(
                    candidates[0].score if candidates else 0.0
                )
        if (
            structured_confidence == "none"
            and not self.settings.no_network
            and self.settings.use_scraper_fallback
            and should_scrape_purl(parsed)
        ):
            scrape_pages = [
                *adapter.fallback_scrape_pages(parsed, metadata),
                *default_fallback_pages(parsed, metadata),
            ]
            try:
                scraped = self.scraper.scrape(parsed, scrape_pages)
            except MetadataFetchError:
                if self.settings.strict:
                    raise
                scraped = []
                warnings.append("Fallback scraping failed")
            scraped_candidates = [
                scraped_to_repository_candidate(candidate) for candidate in scraped
            ]
            scrape_repository_candidates = [
                candidate for candidate in scraped_candidates if candidate is not None
            ]
            if scrape_repository_candidates:
                warnings.append(evidence_messages.used_fallback_scraping())
                evidence.append(evidence_messages.used_fallback_scraping())
                candidates = self._validate_repository_candidates(
                    score_candidates(
                        [*candidates, *scrape_repository_candidates],
                        parsed,
                    ),
                    warnings,
                    evidence,
                )
        best = candidates[0] if candidates else None
        confidence = confidence_from_score(best.score if best else 0.0)

        if best is None:
            warnings.append(evidence_messages.no_repository_warning())
            if self.settings.strict:
                raise NoRepositoryFoundError(f"No repository found for {parsed.raw}")
        elif confidence == "none":
            warnings.append(evidence_messages.weak_candidate_warning())
            if self.settings.strict:
                raise NoRepositoryFoundError(
                    f"Only weak repository candidates found for {parsed.raw}"
                )
        else:
            evidence.append(evidence_messages.selected_candidate())

        if len(candidates) > 1 and best and best.score - candidates[1].score <= 10:
            warnings.append(evidence_messages.ambiguous_warning())

        release_link = None
        if include_release:
            if parsed.version:
                host_adapter = self._host_adapter(best.host if best else "")
                release_link = self._resolve_release_link(
                    adapter=adapter,
                    parsed=parsed,
                    repository=best,
                    metadata=metadata,
                    host_adapter=host_adapter,
                    warnings=warnings,
                    evidence=evidence,
                )
                if release_link:
                    evidence.append(evidence_messages.resolved_release())
                elif best:
                    warnings.append(evidence_messages.no_release_warning())
                    if self.settings.strict:
                        raise NoReleaseFoundError(f"No release link found for {parsed.raw}")
            else:
                warnings.append(evidence_messages.skipped_release_no_version())
                evidence.append(evidence_messages.skipped_release_no_version())

        repository_url = best.normalized_url if best and confidence != "none" else None
        repository_validation_status = self._repository_validation_status(
            repository_url, warnings, evidence
        )

        return ResolutionResult(
            purl=parsed,
            repository_url=repository_url,
            repository_type=best.repository_type if best and confidence != "none" else None,
            repository_kind=(
                _repository_kind_for_candidate(best) if best and confidence != "none" else None
            ),
            repository_candidates=candidates,
            canonical_repository=(
                _repository_ref_from_candidate(best, confidence)
                if best and confidence != "none"
                else None
            ),
            release_link=release_link,
            version_reference=release_link,
            repository_validated=repository_validation_status == "validated",
            repository_validation_status=repository_validation_status,
            confidence=confidence,
            evidence=evidence,
            warnings=warnings,
            metadata_sources=metadata_sources,
        )

    def resolve_repository(self, purl: str) -> ResolutionResult:
        return self.resolve(purl, include_release=False)

    def resolve_release(self, purl: str) -> ResolutionResult:
        result = self.resolve(purl, include_release=True)
        if self.settings.strict and result.release_link is None:
            raise NoReleaseFoundError(f"No release link found for {purl}")
        return result

    def resolve_many(
        self,
        purls: Iterable[str],
        *,
        max_workers: int | None = None,
    ) -> Iterator[ResolutionResult]:
        if max_workers is not None and max_workers < 1:
            raise ValueError("max_workers must be greater than zero")
        if max_workers is None or max_workers == 1:
            for purl in purls:
                yield self.resolve(purl)
            return

        def resolve_one(purl: str) -> ResolutionResult:
            engine = ResolutionEngine(self.settings)
            try:
                return engine.resolve(purl)
            finally:
                engine.close()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            yield from executor.map(resolve_one, purls)

    def _adapter_for(self, parsed: ParsedPurl) -> EcosystemResolver:
        adapter_cls = ECOSYSTEMS.get(parsed.type)
        if not adapter_cls:
            raise UnsupportedEcosystemError(f"Unsupported package type: {parsed.type}")
        return adapter_cls()

    def _resolve_direct_host(
        self, parsed: ParsedPurl, *, include_release: bool
    ) -> ResolutionResult:
        warnings: list[str] = []
        evidence = [f"Resolved {parsed.type} purl directly without repository inference"]
        if not parsed.namespace:
            warnings.append("Direct-host purl is missing a repository namespace")
            if self.settings.strict:
                raise NoRepositoryFoundError(f"No repository found for {parsed.raw}")
            return self._empty_result(parsed, warnings, evidence, [f"{parsed.type}-direct"])

        host = "github.com" if parsed.type == "github" else "bitbucket.org"
        platform = "github" if parsed.type == "github" else "bitbucket"
        url = f"https://{host}/{parsed.namespace}/{parsed.name}"
        candidate = RepositoryCandidate(
            url=url,
            normalized_url=url,
            host=host,
            repository_type=platform,
            source="direct_host",
            score=100.0,
            reasons=[f"Repository identity encoded directly by pkg:{parsed.type} purl"],
        )
        repository = RepositoryRef(
            url=url,
            kind="source_code",
            platform=platform,
            host=host,
            namespace=parsed.namespace,
            name=parsed.name,
            is_canonical=True,
            confidence="high",
            reasons=list(candidate.reasons),
        )
        release_link = None
        if include_release:
            release_link = self._direct_release_link(parsed, candidate, warnings, evidence)
        return self._direct_result(
            parsed=parsed,
            repository=repository,
            candidate=candidate,
            release_link=release_link,
            confidence="high",
            evidence=evidence,
            warnings=warnings,
            metadata_sources=[f"{parsed.type}-direct"],
        )

    def _resolve_artifact_hub(
        self, parsed: ParsedPurl, *, include_release: bool
    ) -> ResolutionResult:
        if parsed.type == "huggingface":
            return self._resolve_huggingface(parsed, include_release=include_release)
        return self._resolve_mlflow(parsed, include_release=include_release)

    def _resolve_huggingface(
        self, parsed: ParsedPurl, *, include_release: bool
    ) -> ResolutionResult:
        repo_path = f"{parsed.namespace}/{parsed.name}" if parsed.namespace else parsed.name
        url = f"https://huggingface.co/{repo_path}"
        evidence = ["Resolved Hugging Face purl to canonical artifact hub repository"]
        warnings: list[str] = []
        candidate = RepositoryCandidate(
            url=url,
            normalized_url=url,
            host="huggingface.co",
            repository_type="huggingface",
            source="artifact_hub",
            score=100.0,
            reasons=["Hugging Face is canonical for pkg:huggingface artifacts"],
        )
        repository = RepositoryRef(
            url=url,
            kind="artifact_hub",
            platform="huggingface",
            host="huggingface.co",
            namespace=parsed.namespace,
            name=parsed.name,
            is_canonical=True,
            confidence="high",
            reasons=list(candidate.reasons),
        )
        release_link = None
        if include_release:
            if parsed.version:
                revision_url = f"{url}/tree/{parsed.version}"
                try:
                    if self.client.url_exists(revision_url):
                        release_link = ReleaseLink(
                            url=revision_url,
                            kind="revision",
                            version=parsed.version,
                            source="huggingface",
                        )
                        evidence.append("Verified Hugging Face revision link exists")
                    else:
                        warnings.append(
                            "Hugging Face revision link could not be verified; "
                            "returning canonical repository only"
                        )
                        if self.settings.strict:
                            raise NoReleaseFoundError(
                                f"No Hugging Face revision link found for {parsed.raw}"
                            )
                except MetadataFetchError:
                    if self.settings.strict:
                        raise
                    warnings.append(
                        "Could not verify Hugging Face revision link; "
                        "returning canonical repository only"
                    )
            else:
                warnings.append(evidence_messages.skipped_release_no_version())
                evidence.append(evidence_messages.skipped_release_no_version())
        return self._direct_result(
            parsed=parsed,
            repository=repository,
            candidate=candidate,
            release_link=release_link,
            confidence="high",
            evidence=evidence,
            warnings=warnings,
            metadata_sources=["huggingface-purl"],
        )

    def _resolve_mlflow(self, parsed: ParsedPurl, *, include_release: bool) -> ResolutionResult:
        registry_url = (
            parsed.qualifiers.get("registry_url")
            or parsed.qualifiers.get("tracking_uri")
            or parsed.qualifiers.get("repository_url")
        )
        evidence = ["Evaluated MLflow purl as artifact hub reference"]
        warnings: list[str] = []
        if not registry_url:
            warnings.append(
                "MLflow purl requires a registry_url, tracking_uri, or repository_url qualifier"
            )
            if self.settings.strict:
                raise NoRepositoryFoundError(f"No MLflow registry URL found for {parsed.raw}")
            return self._empty_result(parsed, warnings, evidence, ["mlflow-purl"])

        url = registry_url.rstrip("/")
        candidate = RepositoryCandidate(
            url=url,
            normalized_url=url,
            host=url_host(url),
            repository_type="mlflow",
            source="artifact_hub",
            score=85.0,
            reasons=["MLflow registry URL supplied by purl qualifier"],
        )
        repository = RepositoryRef(
            url=url,
            kind="artifact_hub",
            platform="mlflow",
            host=url_host(url) or None,
            namespace=parsed.namespace,
            name=parsed.name,
            is_canonical=True,
            confidence="medium",
            reasons=list(candidate.reasons),
        )
        release_link = None
        if include_release:
            if parsed.version:
                release_link = ReleaseLink(
                    url=url,
                    kind="version",
                    version=parsed.version,
                    source="mlflow",
                )
            else:
                warnings.append(evidence_messages.skipped_release_no_version())
                evidence.append(evidence_messages.skipped_release_no_version())
        return self._direct_result(
            parsed=parsed,
            repository=repository,
            candidate=candidate,
            release_link=release_link,
            confidence="medium",
            evidence=evidence,
            warnings=warnings,
            metadata_sources=["mlflow-purl"],
        )

    def _resolve_generic(self, parsed: ParsedPurl, *, include_release: bool) -> ResolutionResult:
        evidence = ["Resolved generic purl from explicit URL qualifiers"]
        warnings: list[str] = []
        selected_key = next(
            (
                key
                for key in ("vcs_url", "repository_url", "download_url")
                if parsed.qualifiers.get(key)
            ),
            None,
        )
        if not selected_key:
            warnings.append(
                "Generic purl requires one of vcs_url, repository_url, or download_url qualifiers"
            )
            if self.settings.strict:
                raise NoRepositoryFoundError(f"No repository qualifier found for {parsed.raw}")
            return self._empty_result(parsed, warnings, evidence, ["generic-purl-qualifiers"])

        source_url = parsed.qualifiers[selected_key]
        repository_source_url = (
            _strip_vcs_revision(source_url) if selected_key == "vcs_url" else source_url
        )
        normalized = repository_source_url.rstrip("/")
        if selected_key != "download_url":
            normalized = normalize_repo_url(repository_source_url) or normalized

        host = url_host(normalized)
        platform = classify_host(host) if host else "generic"
        kind = "vcs" if selected_key in {"vcs_url", "repository_url"} else "generic"
        confidence = "high" if selected_key == "vcs_url" else "medium"
        candidate = RepositoryCandidate(
            url=source_url,
            normalized_url=normalized,
            host=host,
            repository_type=platform,
            source="generic_qualifier",
            score=90.0 if selected_key == "vcs_url" else 70.0,
            reasons=[f"Candidate from generic purl {selected_key} qualifier"],
        )
        repository = RepositoryRef(
            url=normalized,
            kind=kind,
            platform=platform,
            host=host or None,
            namespace=parsed.namespace,
            name=parsed.name,
            is_canonical=selected_key != "download_url",
            confidence=confidence,
            reasons=list(candidate.reasons),
        )
        release_link = None
        if include_release:
            if parsed.version and kind == "vcs":
                release_link = self._direct_release_link(parsed, candidate, warnings, evidence)
            elif not parsed.version:
                warnings.append(evidence_messages.skipped_release_no_version())
                evidence.append(evidence_messages.skipped_release_no_version())
        return self._direct_result(
            parsed=parsed,
            repository=repository,
            candidate=candidate,
            release_link=release_link,
            confidence=confidence,
            evidence=evidence,
            warnings=warnings,
            metadata_sources=["generic-purl-qualifiers"],
        )

    def _host_adapter(self, host: str) -> HostAdapter | None:
        if not host:
            return None
        return HOSTS.get(host, GENERIC_HOST)

    def _resolve_release_link(
        self,
        *,
        adapter: EcosystemResolver,
        parsed: ParsedPurl,
        repository: RepositoryCandidate | None,
        metadata: Metadata,
        host_adapter: HostAdapter | None,
        warnings: list[str],
        evidence: list[str],
    ) -> ReleaseLink | None:
        if host_adapter is None or not parsed.version:
            return None
        if not self.settings.verify_release_links:
            return adapter.resolve_release_link(parsed, repository, metadata, host_adapter)

        if repository is None:
            return None
        try:
            candidates = host_adapter.candidate_release_links(
                repository.normalized_url,
                parsed.version,
            )
            for candidate in candidates:
                if self.client.url_exists(candidate.url):
                    evidence.append(evidence_messages.verified_release())
                    return candidate
        except MetadataFetchError:
            if self.settings.strict:
                raise
            warnings.append("Could not verify inferred release links")
            return None
        warnings.append(evidence_messages.unverified_release_warning())
        return None

    def _direct_release_link(
        self,
        parsed: ParsedPurl,
        candidate: RepositoryCandidate,
        warnings: list[str],
        evidence: list[str],
    ) -> ReleaseLink | None:
        if not parsed.version:
            warnings.append(evidence_messages.skipped_release_no_version())
            evidence.append(evidence_messages.skipped_release_no_version())
            return None
        host_adapter = self._host_adapter(candidate.host)
        if host_adapter is None:
            return None
        if self.settings.verify_release_links:
            try:
                for release_candidate in host_adapter.candidate_release_links(
                    candidate.normalized_url,
                    parsed.version,
                ):
                    if self.client.url_exists(release_candidate.url):
                        evidence.append(evidence_messages.verified_release())
                        return release_candidate
            except MetadataFetchError:
                if self.settings.strict:
                    raise
                warnings.append("Could not verify inferred release links")
                return None
            warnings.append(evidence_messages.unverified_release_warning())
            return None
        return host_adapter.infer_release_link(candidate.normalized_url, parsed.version)

    def _direct_result(
        self,
        *,
        parsed: ParsedPurl,
        repository: RepositoryRef,
        candidate: RepositoryCandidate,
        release_link: ReleaseLink | None,
        confidence: str,
        evidence: list[str],
        warnings: list[str],
        metadata_sources: list[str],
    ) -> ResolutionResult:
        if release_link:
            evidence.append(evidence_messages.resolved_release())
        if not self._repository_url_is_valid(repository.url, warnings, evidence):
            if self.settings.strict:
                raise NoRepositoryFoundError(f"Repository URL did not validate: {repository.url}")
            return self._empty_result(parsed, warnings, evidence, metadata_sources)
        repository_validation_status = self._repository_validation_status(
            repository.url, warnings, evidence
        )

        return ResolutionResult(
            purl=parsed,
            repository_url=repository.url,
            repository_type=repository.platform,
            repository_kind=repository.kind,
            repository_candidates=[candidate],
            canonical_repository=repository,
            release_link=release_link,
            version_reference=release_link,
            repository_validated=repository_validation_status == "validated",
            repository_validation_status=repository_validation_status,
            confidence=confidence,
            evidence=evidence,
            warnings=warnings,
            metadata_sources=metadata_sources,
        )

    def _validate_repository_candidates(
        self,
        candidates: list[RepositoryCandidate],
        warnings: list[str],
        evidence: list[str],
    ) -> list[RepositoryCandidate]:
        validated: list[RepositoryCandidate] = []
        for candidate in candidates:
            validated_candidate = self._validate_repository_candidate(candidate, warnings, evidence)
            if validated_candidate is not None:
                validated.append(validated_candidate)
        return validated

    def _validate_repository_candidate(
        self,
        candidate: RepositoryCandidate,
        warnings: list[str],
        evidence: list[str],
    ) -> RepositoryCandidate | None:
        if self.settings.no_network:
            return candidate
        if not self.settings.validate_repositories:
            message = "Repository URL validation skipped by settings"
            if message not in evidence:
                evidence.append(message)
            return candidate
        try:
            if self.client.url_exists(candidate.normalized_url, ttl_seconds=86400):
                evidence.append(f"Validated repository URL: {candidate.normalized_url}")
                return candidate
        except MetadataFetchError:
            if self.settings.strict:
                raise
            warnings.append(f"Could not validate repository URL: {candidate.normalized_url}")
            return replace(
                candidate,
                score=min(candidate.score, 64.0),
                reasons=[
                    *candidate.reasons,
                    "Repository URL validation was inconclusive; confidence capped below medium",
                ],
            )
        warnings.append(
            f"Repository URL did not validate and was discarded: {candidate.normalized_url}"
        )
        return None

    def _repository_url_is_valid(
        self,
        url: str,
        warnings: list[str],
        evidence: list[str],
    ) -> bool:
        if self.settings.no_network:
            return True
        if not self.settings.validate_repositories:
            message = "Repository URL validation skipped by settings"
            if message not in evidence:
                evidence.append(message)
            return True
        try:
            if self.client.url_exists(url, ttl_seconds=86400):
                evidence.append(f"Validated repository URL: {url}")
                return True
        except MetadataFetchError:
            if self.settings.strict:
                raise
            warnings.append(f"Could not validate repository URL: {url}")
            return True
        warnings.append(f"Repository URL did not validate and was discarded: {url}")
        return False

    def _repository_validation_status(
        self,
        repository_url: str | None,
        warnings: list[str],
        evidence: list[str],
    ) -> str:
        if repository_url is None:
            return "not_applicable"
        if self.settings.no_network or not self.settings.validate_repositories:
            return "skipped"
        if f"Validated repository URL: {repository_url}" in evidence:
            return "validated"
        if any(f"Could not validate repository URL: {repository_url}" in item for item in warnings):
            return "inconclusive"
        if any(
            "Repository URL did not validate and was discarded" in item and repository_url in item
            for item in warnings
        ):
            return "failed"
        return "unknown"

    def _empty_result(
        self,
        parsed: ParsedPurl,
        warnings: list[str],
        evidence: list[str],
        metadata_sources: list[str],
    ) -> ResolutionResult:
        return ResolutionResult(
            purl=parsed,
            repository_url=None,
            repository_type=None,
            repository_kind=None,
            repository_candidates=[],
            canonical_repository=None,
            release_link=None,
            version_reference=None,
            repository_validated=False,
            repository_validation_status="not_applicable",
            confidence="none",
            evidence=evidence,
            warnings=warnings,
            metadata_sources=metadata_sources,
        )


def _repository_kind_for_candidate(candidate: RepositoryCandidate) -> str:
    if candidate.repository_type in {"github", "gitlab", "bitbucket", "generic_git"}:
        return "source_code"
    return "generic"


def _strip_vcs_revision(url: str) -> str:
    coerced = coerce_git_url(url)
    parsed = urlsplit(coerced)
    if parsed.scheme not in {"http", "https", "ssh"} or "@" not in parsed.path:
        return url
    path, revision = parsed.path.rsplit("@", 1)
    if "/" not in path or not revision:
        return url
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))


def _repository_ref_from_candidate(
    candidate: RepositoryCandidate, confidence: str
) -> RepositoryRef:
    parts = [part for part in urlsplit(candidate.normalized_url).path.split("/") if part]
    namespace = "/".join(parts[:-1]) if len(parts) >= 2 else None
    name = parts[-1] if parts else None
    return RepositoryRef(
        url=candidate.normalized_url,
        kind=_repository_kind_for_candidate(candidate),
        platform=candidate.repository_type,
        host=candidate.host or None,
        namespace=namespace,
        name=name,
        is_canonical=True,
        confidence=confidence,
        reasons=list(candidate.reasons),
    )
