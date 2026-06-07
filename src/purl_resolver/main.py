from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from fastapi import FastAPI

from .config import settings, storage_settings
from .resolver.factory import build_resolvers
from .settings_store import SettingsStore
from .router import router
from .storage.inmemory import InMemoryCache
from .storage.postgres import PostgresCache, create_pool

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = None
    try:
        pool = await create_pool()
        app.state.storage = PostgresCache(pool)
        logger.info("Connected to PostgreSQL at %s", storage_settings.url)
    except (asyncpg.InvalidCatalogNameError, OSError, Exception):
        logger.warning(
            "PostgreSQL unavailable, falling back to in-memory cache", exc_info=True
        )
        app.state.storage = InMemoryCache()
    app.state.settings_store = SettingsStore()

    app_settings = app.state.settings_store.load()
    app.state.resolvers = build_resolvers(settings, app_settings)

    logger.info("Configured %d resolver(s)", len(app.state.resolvers))
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="sbom-helper", lifespan=lifespan)
app.include_router(router)


def main() -> None:
    import os

    ssl_keyfile = os.environ.get("SSL_KEYFILE")
    ssl_certfile = os.environ.get("SSL_CERTFILE")

    kwargs: dict = {
        "host": "0.0.0.0",
        "port": 8443,
        "reload": True,
    }

    if ssl_keyfile and ssl_certfile:
        kwargs["ssl_keyfile"] = ssl_keyfile
        kwargs["ssl_certfile"] = ssl_certfile

    uvicorn.run("purl_resolver.main:app", **kwargs)


if __name__ == "__main__":
    main()
