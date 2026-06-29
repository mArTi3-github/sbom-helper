from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import asyncpg
import pathlib
import uvicorn

from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


class SPAStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException:
            if self.html:
                return await super().get_response("index.html", scope)
            raise

from .config import settings, storage_settings
from .db_admin_service import DbAdminService
from .ignore_patterns_store import IgnorePatternsStore
from .resolver.factory import build_resolvers
from .router import router
from .service import PurlResolutionService
from .settings_store import SettingsStore
from .storage.inmemory import InMemoryCache
from .storage.postgres import PostgresCache, create_pool
from .validation_service import UrlValidationService

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
    app.state.ignore_patterns_store = IgnorePatternsStore()

    app_settings = app.state.settings_store.load()
    logging.basicConfig(level=app_settings.log_level_as_int(), force=True)
    app.state.resolvers = build_resolvers(settings, app_settings)
    app.state.db_admin_service = DbAdminService(app.state.storage)
    app.state.validation_service = UrlValidationService(app.state.settings_store)
    app.state.resolution_service = PurlResolutionService(
        storage=app.state.storage,
        resolvers=app.state.resolvers,
        settings_store=app.state.settings_store,
        validation_service=app.state.validation_service,
    )

    spa_dir = pathlib.Path("/app/frontend/dist")
    if spa_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(spa_dir), html=True), name="spa")
        logger.info("Serving SPA from %s", spa_dir)
    else:
        logger.warning("No SPA directory found — frontend will not be served")

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
