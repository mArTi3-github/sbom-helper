from __future__ import annotations

import logging
from urllib.parse import quote

import httpx

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)

_API_URL = "https://packages.ecosyste.ms/api/v1/packages/lookup"


def select_repository_url(package_data: dict) -> str | None:
    candidates = [
        package_data.get("repository_url", ""),
        package_data.get("registry_url", ""),
        package_data.get("homepage", ""),
    ]

    for url in candidates:
        if not url or "repos.ecosyste.ms" in url:
            continue
        if "github.com" in url:
            return url

    for url in candidates:
        if url and "repos.ecosyste.ms" not in url:
            return url

    return None


class EcosystemsResolver(Resolver):

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.Client(timeout=timeout)

    @property
    def name(self) -> str:
        return "ecosyste.ms"

    def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        params: dict[str, str] = {"purl": purl}
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            response = self._client.get(_API_URL, params=params)
            response.raise_for_status()
        except httpx.TimeoutException:
            logger.warning("ecosyste.ms request timed out for %s", purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms timeout for {purl}"])
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.warning("ecosyste.ms returned %d for %s", status, purl)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms error {status} for {purl}"])
        except httpx.HTTPError as exc:
            logger.warning("ecosyste.ms request failed for %s: %s", purl, exc)
            return Resolution(purl=purl, warnings=[f"ecosyste.ms network error for {purl}: {exc}"])

        data = response.json()
        if not data:
            return Resolution(purl=purl, warnings=[f"No package found on ecosyste.ms for {purl}"])

        package = data[0]
        repo_url = select_repository_url(package)
        if not repo_url:
            return Resolution(purl=purl, warnings=[f"No repository URL found on ecosyste.ms for {purl}"])

        ecosystem = package.get("ecosystem", "unknown")
        name = package.get("name", "unknown")

        return Resolution(
            purl=purl,
            repository_url=repo_url,
            repository_type=None,
            repository_kind="vcs",
            confidence="medium",
            evidence=[f"ecosyste.ms:{ecosystem}/{name}"],
        )
