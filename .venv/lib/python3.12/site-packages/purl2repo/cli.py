"""Typer command-line interface."""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

import typer

from purl2repo import api
from purl2repo.errors import (
    InvalidPurlError,
    MetadataFetchError,
    NoReleaseFoundError,
    NoRepositoryFoundError,
    Purl2RepoError,
    UnsupportedEcosystemError,
)
from purl2repo.models import ResolutionResult, ResolverSettings
from purl2repo.resolution.engine import ECOSYSTEMS, HOSTS, SUPPORTED_PURL_TYPES
from purl2repo.version import __version__

app = typer.Typer(help="Resolve Package URLs to source repositories and release links.")

JsonOption = Annotated[bool, typer.Option("--json", help="Emit stable JSON output.")]
PrettyOption = Annotated[bool, typer.Option("--pretty", help="Pretty-print JSON output.")]
StrictOption = Annotated[
    bool,
    typer.Option("--strict/--no-strict", help="Raise on weak or incomplete resolution."),
]
TimeoutOption = Annotated[float, typer.Option("--timeout", help="HTTP timeout in seconds.")]
NoCacheOption = Annotated[bool, typer.Option("--no-cache", help="Disable resolver cache.")]
CacheDirOption = Annotated[
    str | None,
    typer.Option("--cache-dir", help="Optional disk cache directory."),
]
VerboseOption = Annotated[bool, typer.Option("--verbose", help="Enable debug logging.")]
TraceOption = Annotated[bool, typer.Option("--trace", help="Include candidate scoring details.")]
NoNetworkOption = Annotated[
    bool,
    typer.Option("--no-network", help="Use cache only; do not fetch."),
]
VerifyReleaseOption = Annotated[
    bool,
    typer.Option(
        "--verify-release-links/--no-verify-release-links",
        help="Check inferred release URLs before returning them.",
    ),
]
ValidateRepositoriesOption = Annotated[
    bool,
    typer.Option(
        "--validate-repositories/--no-validate-repositories",
        help="Check candidate repository URLs before selecting them.",
    ),
]
DepsDevFallbackOption = Annotated[
    bool,
    typer.Option(
        "--deps-dev-fallback/--no-deps-dev-fallback",
        help="Use deps.dev as a third-party fallback when first-party metadata has no repo.",
    ),
]
ScraperFallbackOption = Annotated[
    bool,
    typer.Option(
        "--scraper-fallback/--no-scraper-fallback",
        help="Use bounded HTML scraping when structured and deps.dev fallbacks have no repo.",
    ),
]


def _settings(
    timeout: float,
    no_cache: bool,
    cache_dir: str | None,
    strict: bool,
    no_network: bool,
    verify_release_links: bool,
    validate_repositories: bool,
    use_deps_dev_fallback: bool,
    use_scraper_fallback: bool,
) -> ResolverSettings:
    return ResolverSettings(
        timeout=timeout,
        use_cache=not no_cache,
        cache_dir=cache_dir,
        strict=strict,
        no_network=no_network,
        verify_release_links=verify_release_links,
        validate_repositories=validate_repositories,
        use_deps_dev_fallback=use_deps_dev_fallback,
        use_scraper_fallback=use_scraper_fallback,
    )


def _resolver(settings: ResolverSettings) -> api.Resolver:
    return api.Resolver(
        timeout=settings.timeout,
        use_cache=settings.use_cache,
        cache_dir=settings.cache_dir,
        strict=settings.strict,
        no_network=settings.no_network,
        verify_release_links=settings.verify_release_links,
        validate_repositories=settings.validate_repositories,
        use_deps_dev_fallback=settings.use_deps_dev_fallback,
        use_scraper_fallback=settings.use_scraper_fallback,
        user_agent=settings.user_agent,
    )


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.WARNING)


def _emit(data: Any, *, json_output: bool, pretty: bool) -> None:
    if json_output:
        typer.echo(json.dumps(data, indent=2 if pretty else None, sort_keys=pretty))
    elif isinstance(data, dict):
        for key, value in data.items():
            typer.echo(f"{key}: {value}")
    else:
        typer.echo(str(data))


def _emit_result(result: ResolutionResult, *, json_output: bool, pretty: bool, trace: bool) -> None:
    if json_output:
        payload = result.to_dict()
        if not trace:
            payload = dict(payload)
        _emit(payload, json_output=True, pretty=pretty)
        return

    typer.echo(f"Repository: {result.repository_url or 'not found'}")
    typer.echo(f"Kind: {result.repository_kind or 'unknown'}")
    typer.echo(f"Type: {result.repository_type or 'unknown'}")
    if result.release_link and result.release_link.version:
        typer.echo(f"Version: {result.release_link.version}")
    typer.echo(f"Release: {result.release_link.url if result.release_link else 'not found'}")
    typer.echo(f"Confidence: {result.confidence}")
    if result.evidence:
        typer.echo("Evidence:")
        for item in result.evidence:
            typer.echo(f"- {item}")
    if result.warnings:
        typer.echo("Warnings:")
        for item in result.warnings:
            typer.echo(f"- {item}")
    if trace and result.repository_candidates:
        typer.echo("")
        typer.echo("Candidates:")
        for index, candidate in enumerate(result.repository_candidates, start=1):
            typer.echo(f"{index}. {candidate.normalized_url} (score: {candidate.score:g})")
            for reason in candidate.reasons:
                typer.echo(f"   - {reason}")


def _handle_error(exc: Purl2RepoError) -> None:
    if isinstance(exc, InvalidPurlError):
        raise typer.Exit(2) from exc
    if isinstance(exc, UnsupportedEcosystemError):
        raise typer.Exit(3) from exc
    if isinstance(exc, MetadataFetchError):
        raise typer.Exit(5) from exc
    if isinstance(exc, NoRepositoryFoundError | NoReleaseFoundError):
        raise typer.Exit(4) from exc
    raise typer.Exit(4) from exc


@app.command()
def parse(
    purl: str,
    json_output: JsonOption = False,
    pretty: PrettyOption = False,
) -> None:
    """Parse and validate a Package URL."""

    try:
        parsed = api.parse_purl(purl)
    except Purl2RepoError as exc:
        typer.echo(str(exc), err=True)
        _handle_error(exc)
    _emit(parsed.to_dict(), json_output=json_output, pretty=pretty)


@app.command()
def resolve(
    purl: str,
    json_output: JsonOption = False,
    pretty: PrettyOption = False,
    strict: StrictOption = False,
    timeout: TimeoutOption = 10.0,
    no_cache: NoCacheOption = False,
    cache_dir: CacheDirOption = None,
    verbose: VerboseOption = False,
    trace: TraceOption = False,
    no_network: NoNetworkOption = False,
    verify_release_links: VerifyReleaseOption = False,
    validate_repositories: ValidateRepositoriesOption = True,
    deps_dev_fallback: DepsDevFallbackOption = True,
    scraper_fallback: ScraperFallbackOption = True,
) -> None:
    """Resolve repository and release information."""

    _configure_logging(verbose)
    settings = _settings(
        timeout,
        no_cache,
        cache_dir,
        strict,
        no_network,
        verify_release_links,
        validate_repositories,
        deps_dev_fallback,
        scraper_fallback,
    )
    try:
        with _resolver(settings) as resolver:
            result = resolver.resolve(purl)
    except Purl2RepoError as exc:
        typer.echo(str(exc), err=True)
        _handle_error(exc)
    _emit_result(result, json_output=json_output, pretty=pretty, trace=trace)


@app.command()
def repo(
    purl: str,
    json_output: JsonOption = False,
    pretty: PrettyOption = False,
    strict: StrictOption = False,
    timeout: TimeoutOption = 10.0,
    no_cache: NoCacheOption = False,
    cache_dir: CacheDirOption = None,
    verbose: VerboseOption = False,
    trace: TraceOption = False,
    no_network: NoNetworkOption = False,
    verify_release_links: VerifyReleaseOption = False,
    validate_repositories: ValidateRepositoriesOption = True,
    deps_dev_fallback: DepsDevFallbackOption = True,
    scraper_fallback: ScraperFallbackOption = True,
) -> None:
    """Resolve the best repository only."""

    _configure_logging(verbose)
    settings = _settings(
        timeout,
        no_cache,
        cache_dir,
        strict,
        no_network,
        verify_release_links,
        validate_repositories,
        deps_dev_fallback,
        scraper_fallback,
    )
    try:
        with _resolver(settings) as resolver:
            result = resolver.resolve_repository(purl)
    except Purl2RepoError as exc:
        typer.echo(str(exc), err=True)
        _handle_error(exc)
    _emit_result(result, json_output=json_output, pretty=pretty, trace=trace)


@app.command()
def release(
    purl: str,
    json_output: JsonOption = False,
    pretty: PrettyOption = False,
    strict: StrictOption = False,
    timeout: TimeoutOption = 10.0,
    no_cache: NoCacheOption = False,
    cache_dir: CacheDirOption = None,
    verbose: VerboseOption = False,
    trace: TraceOption = False,
    no_network: NoNetworkOption = False,
    verify_release_links: VerifyReleaseOption = False,
    validate_repositories: ValidateRepositoriesOption = True,
    deps_dev_fallback: DepsDevFallbackOption = True,
    scraper_fallback: ScraperFallbackOption = True,
) -> None:
    """Resolve a version-specific release or source link."""

    _configure_logging(verbose)
    settings = _settings(
        timeout,
        no_cache,
        cache_dir,
        strict,
        no_network,
        verify_release_links,
        validate_repositories,
        deps_dev_fallback,
        scraper_fallback,
    )
    try:
        with _resolver(settings) as resolver:
            result = resolver.resolve_release(purl)
    except Purl2RepoError as exc:
        typer.echo(str(exc), err=True)
        _handle_error(exc)
    _emit_result(result, json_output=json_output, pretty=pretty, trace=trace)


@app.command()
def supports(json_output: JsonOption = False, pretty: PrettyOption = False) -> None:
    """List supported ecosystems and recognized repository hosts."""

    payload = {
        "ecosystems": sorted(ECOSYSTEMS),
        "purl_types": sorted(SUPPORTED_PURL_TYPES),
        "hosts": [*sorted(HOSTS), "generic"],
    }
    if json_output:
        _emit(payload, json_output=True, pretty=pretty)
    else:
        typer.echo("Supported ecosystems:")
        for ecosystem in payload["ecosystems"]:
            typer.echo(f"- {ecosystem}")
        typer.echo("Recognized hosts:")
        for host in payload["hosts"]:
            typer.echo(f"- {host}")


@app.command()
def version() -> None:
    """Print purl2repo version."""

    typer.echo(__version__)


if __name__ == "__main__":
    app()
