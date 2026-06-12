from __future__ import annotations

from ..config import Settings
from ..settings_store import AppSettings
from .ecosystems import EcosystemsResolver
from .interface import Resolver
from .librariesio import LibrariesIoResolver
from .purl2repo import Purl2RepoResolver
from .retry import RetryConfig


def build_resolvers(
    settings: Settings,
    app_settings: AppSettings,
) -> list[Resolver]:
    resolvers: list[Resolver] = [
        Purl2RepoResolver(
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        ),
    ]
    retry_config = RetryConfig(
        max_attempts=app_settings.retry_max_attempts,
        base_cooldown_seconds=app_settings.retry_base_cooldown_seconds,
    )
    if app_settings.ecosystems_enabled:
        resolvers.append(
            EcosystemsResolver(
                api_key=app_settings.ecosystems_api_key,
                max_requests_per_second=app_settings.ecosystems_max_requests_per_second,
                retry_config=retry_config,
            )
        )
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        resolvers.append(
            LibrariesIoResolver(api_key=app_settings.librariesio_api_key, retry_config=retry_config)
        )
    return resolvers
