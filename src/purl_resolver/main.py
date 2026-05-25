from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncpg
import uvicorn
from fastapi import FastAPI

from .config import settings, storage_settings
from .resolver.purl2repo import Purl2RepoResolver
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
    app.state.resolvers = [
        Purl2RepoResolver(
            timeout=settings.timeout,
            use_cache=settings.use_cache,
            strict=settings.strict,
            no_network=settings.no_network,
            cache_dir=settings.cache_dir,
        ),
    ]
    logger.info("Configured %d resolver(s)", len(app.state.resolvers))
    yield
    if pool is not None:
        await pool.close()


app = FastAPI(title="sbom-helper", lifespan=lifespan)
app.include_router(router)


def main() -> None:
    uvicorn.run(
        "purl_resolver.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
