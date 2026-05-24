"""Public Python API."""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from purl2repo.models import ParsedPurl, ResolutionResult, ResolverSettings
from purl2repo.purl.parse import parse_purl as _parse_purl
from purl2repo.resolution.engine import ResolutionEngine


def parse_purl(purl: str) -> ParsedPurl:
    """Parse and validate a Package URL without resolving metadata."""

    return _parse_purl(purl)


def resolve_repository(purl: str, **kwargs: object) -> ResolutionResult:
    """Resolve only the best repository for a Package URL."""

    with _resolver_from_kwargs(kwargs) as resolver:
        return resolver.resolve_repository(purl)


def resolve_release(purl: str, **kwargs: object) -> ResolutionResult:
    """Resolve a version-specific release link, including repository context."""

    with _resolver_from_kwargs(kwargs) as resolver:
        return resolver.resolve_release(purl)


def resolve(purl: str, **kwargs: object) -> ResolutionResult:
    """Resolve repository and version-specific release information."""

    with _resolver_from_kwargs(kwargs) as resolver:
        return resolver.resolve(purl)


def _resolver_from_kwargs(kwargs: dict[str, object]) -> Resolver:
    allowed = {
        "timeout",
        "use_cache",
        "cache_dir",
        "strict",
        "no_network",
        "verify_release_links",
        "validate_repositories",
        "use_deps_dev_fallback",
        "use_scraper_fallback",
        "user_agent",
    }
    unknown = set(kwargs) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise TypeError(f"Unknown resolver option(s): {names}")

    timeout = kwargs.get("timeout", 10.0)
    use_cache = kwargs.get("use_cache", True)
    cache_dir = kwargs.get("cache_dir")
    strict = kwargs.get("strict", False)
    no_network = kwargs.get("no_network", False)
    verify_release_links = kwargs.get("verify_release_links", False)
    validate_repositories = kwargs.get("validate_repositories", True)
    use_deps_dev_fallback = kwargs.get("use_deps_dev_fallback", True)
    use_scraper_fallback = kwargs.get("use_scraper_fallback", True)
    user_agent = kwargs.get("user_agent", "purl2repo/2.x")

    if not isinstance(timeout, int | float):
        raise TypeError("timeout must be a number")
    if not isinstance(use_cache, bool):
        raise TypeError("use_cache must be a bool")
    if cache_dir is not None and not isinstance(cache_dir, str):
        raise TypeError("cache_dir must be a string or None")
    if not isinstance(strict, bool):
        raise TypeError("strict must be a bool")
    if not isinstance(no_network, bool):
        raise TypeError("no_network must be a bool")
    if not isinstance(verify_release_links, bool):
        raise TypeError("verify_release_links must be a bool")
    if not isinstance(validate_repositories, bool):
        raise TypeError("validate_repositories must be a bool")
    if not isinstance(use_deps_dev_fallback, bool):
        raise TypeError("use_deps_dev_fallback must be a bool")
    if not isinstance(use_scraper_fallback, bool):
        raise TypeError("use_scraper_fallback must be a bool")
    if not isinstance(user_agent, str):
        raise TypeError("user_agent must be a string")

    return Resolver(
        timeout=float(timeout),
        use_cache=use_cache,
        cache_dir=cache_dir,
        strict=strict,
        no_network=no_network,
        verify_release_links=verify_release_links,
        validate_repositories=validate_repositories,
        use_deps_dev_fallback=use_deps_dev_fallback,
        use_scraper_fallback=use_scraper_fallback,
        user_agent=user_agent,
    )


class Resolver:
    """Reusable configured resolver for single or batch usage."""

    def __init__(
        self,
        timeout: float = 10.0,
        use_cache: bool = True,
        cache_dir: str | None = None,
        strict: bool = False,
        no_network: bool = False,
        verify_release_links: bool = False,
        validate_repositories: bool = True,
        use_deps_dev_fallback: bool = True,
        use_scraper_fallback: bool = True,
        user_agent: str = "purl2repo/2.x",
    ) -> None:
        self.settings = ResolverSettings(
            timeout=timeout,
            use_cache=use_cache,
            cache_dir=cache_dir,
            strict=strict,
            no_network=no_network,
            verify_release_links=verify_release_links,
            validate_repositories=validate_repositories,
            use_deps_dev_fallback=use_deps_dev_fallback,
            use_scraper_fallback=use_scraper_fallback,
            user_agent=user_agent,
        )
        self._engine = ResolutionEngine(self.settings)

    def __enter__(self) -> Resolver:
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()

    def close(self) -> None:
        self._engine.close()

    def parse_purl(self, purl: str) -> ParsedPurl:
        return self._engine.parse(purl)

    def resolve(self, purl: str) -> ResolutionResult:
        return self._engine.resolve(purl)

    def resolve_repository(self, purl: str) -> ResolutionResult:
        return self._engine.resolve_repository(purl)

    def resolve_release(self, purl: str) -> ResolutionResult:
        return self._engine.resolve_release(purl)

    def resolve_many(
        self,
        iterable_of_purls: Iterable[str],
        *,
        max_workers: int | None = None,
    ) -> Iterator[ResolutionResult]:
        return self._engine.resolve_many(iterable_of_purls, max_workers=max_workers)
