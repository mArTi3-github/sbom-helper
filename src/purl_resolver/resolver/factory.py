from __future__ import annotations

import logging

from ..config import Settings
from ..settings_store import AppSettings
from .apk import ApkResolver
from .depsdev import DepsdevResolver
from .ecosystems import EcosystemsResolver
from .interface import Resolver
from .librariesio import LibrariesIoResolver
from .llm import LlmResolver
from .purl2repo import Purl2RepoResolver
from .retry import RetryConfig

logger = logging.getLogger(__name__)


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
    if app_settings.depsdev_enabled:
        resolvers.append(
            DepsdevResolver(
                timeout=settings.timeout,
                retry_config=retry_config,
            )
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
    if app_settings.apk_resolver_enabled:
        resolvers.append(ApkResolver())
    if app_settings.llm_resolver_enabled:
        missing = [
            name
            for name, value in (
                ("llm_resolver_base_url", app_settings.llm_resolver_base_url),
                ("llm_resolver_api_key", app_settings.llm_resolver_api_key),
                ("llm_resolver_model", app_settings.llm_resolver_model),
            )
            if not value
        ]
        if missing:
            logger.warning(
                "LLM resolver is enabled but not added to the chain: missing %s",
                ", ".join(missing),
            )
        else:
            resolvers.append(
                LlmResolver(
                    base_url=app_settings.llm_resolver_base_url,
                    api_key=app_settings.llm_resolver_api_key,
                    model=app_settings.llm_resolver_model,
                    attempts_count=app_settings.llm_resolver_attempts_count,
                    timeout=app_settings.llm_resolver_timeout,
                )
            )
            logger.info("LLM resolver added as the last resolver in the chain")
    return resolvers
