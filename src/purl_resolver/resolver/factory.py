from __future__ import annotations

from ..config import Settings
from ..settings_store import AppSettings
from .ecosystems import EcosystemsResolver
from .interface import Resolver
from .librariesio import LibrariesIoResolver
from .purl2repo import Purl2RepoResolver


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
    if app_settings.ecosystems_enabled:
        resolvers.append(
            EcosystemsResolver(api_key=app_settings.ecosystems_api_key)
        )
    if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
        resolvers.append(
            LibrariesIoResolver(api_key=app_settings.librariesio_api_key)
        )
    return resolvers
