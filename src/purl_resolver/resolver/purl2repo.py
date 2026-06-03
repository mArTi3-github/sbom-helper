from __future__ import annotations

import logging

from purl2repo import resolve as purl2repo_resolve
from purl2repo.errors import (
    InvalidPurlError as Purl2RepoInvalidPurlError,
)
from purl2repo.errors import (
    MetadataFetchError,
    UnsupportedEcosystemError,
)
from purl2repo.errors import (
    ResolutionError as Purl2RepoResolutionError,
)

from .interface import InvalidPurlError, Resolution, Resolver, UpstreamError

logger = logging.getLogger(__name__)


class Purl2RepoResolver(Resolver):

    def __init__(
        self,
        timeout: float = 15.0,
        use_cache: bool = True,
        strict: bool = False,
        no_network: bool = False,
        cache_dir: str | None = None,
    ) -> None:
        self._timeout = timeout
        self._use_cache = use_cache
        self._strict = strict
        self._no_network = no_network
        self._cache_dir = cache_dir

    def resolve(self, purl: str) -> Resolution:
        try:
            result = purl2repo_resolve(
                purl,
                timeout=self._timeout,
                use_cache=self._use_cache,
                strict=self._strict,
                no_network=self._no_network,
                cache_dir=self._cache_dir,
            )
        except UnsupportedEcosystemError as e:
            logger.info("purl2repo does not support type %s, skipping", purl.split(":")[1].split("/")[0] if ":" in purl else "?")
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type for purl2repo: {e}"],
            )
        except Purl2RepoInvalidPurlError as e:
            raise InvalidPurlError(str(e)) from e
        except (Purl2RepoResolutionError, MetadataFetchError) as e:
            raise UpstreamError(str(e)) from e
        return Resolution(
            purl=purl,
            repository_url=result.repository_url,
            repository_type=result.repository_type,
            repository_kind=result.repository_kind,
            confidence=result.confidence,
            evidence=list(result.evidence),
            warnings=list(result.warnings),
            version_reference=result.version_reference.url
            if result.version_reference
            else None,
        )
