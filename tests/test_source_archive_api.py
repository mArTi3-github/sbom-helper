from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from purl_resolver.resolver.interface import Resolution
from purl_resolver.router import router
from purl_resolver.service import PurlResolutionService
from purl_resolver.settings_store import SettingsStore
from purl_resolver.source_archive.matching import TagInfo
from purl_resolver.source_archive.service import SourceArchiveService
from purl_resolver.storage.inmemory import InMemoryCache
from purl_resolver.storage.inmemory_source_archive import InMemorySourceArchiveStorage
from tests.helpers import FakeResolver

PURL = "pkg:github/ClickHouse/ClickHouse@23.8.16.40"
REPO = "https://github.com/ClickHouse/ClickHouse"
TAG_SHA = "e143a9039ba36ad0c25f2ed85503f36e88f61063"
TAGS = [TagInfo("v23.8.16.40-lts", TAG_SHA)]


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    test_app = FastAPI()
    test_app.state.storage = InMemoryCache()
    test_app.state.resolvers = [
        FakeResolver(
            resolution=Resolution(purl=PURL, repository_url=REPO),
        ),
    ]
    test_app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
    test_app.state.resolution_service = PurlResolutionService(
        storage=test_app.state.storage,
        resolvers=test_app.state.resolvers,
        settings_store=test_app.state.settings_store,
    )

    async def fetcher(url: str, timeout: float) -> list[TagInfo]:
        return list(TAGS)

    async def checker(url: str, timeout: float) -> bool:
        return True

    test_app.state.source_archive_service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=test_app.state.settings_store,
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    test_app.include_router(router)
    with TestClient(test_app) as c:
        yield c


def test_flag_off_keeps_response_unchanged(client):
    data = client.post("/api/v1/resolve/batch", json={"purls": [PURL]}).json()
    item = data["results"][0]
    assert item["repository_url"] == REPO
    assert item["source_archive_url"] is None
    assert item["source_archive_match"] is None


def test_flag_on_returns_exact_archive(client):
    data = client.post("/api/v1/resolve/batch", json={
        "purls": [PURL], "find_source_archive": True,
    }).json()
    item = data["results"][0]
    assert item["source_archive_match"] == "exact"
    assert item["source_archive_ref"] == "v23.8.16.40-lts"
    assert item["source_archive_url"].endswith("/archive/refs/tags/v23.8.16.40-lts.tar.gz")
    assert item["source_archive_cached"] is False


def test_second_request_is_cached(client):
    client.post("/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True})
    data = client.post(
        "/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True}
    ).json()
    assert data["results"][0]["source_archive_cached"] is True


def test_force_refresh_recomputes(client):
    client.post("/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True})
    data = client.post("/api/v1/resolve/batch", json={
        "purls": [PURL], "find_source_archive": True, "force_refresh": True,
    }).json()
    assert data["results"][0]["source_archive_cached"] is False


def test_invalid_purl_keeps_archive_fields_null(client):
    data = client.post("/api/v1/resolve/batch", json={
        "purls": ["not-a-purl"], "find_source_archive": True,
    }).json()
    assert data["results"][0]["error"] == "invalid_purl"
    assert data["results"][0]["source_archive_match"] is None


def test_mixed_rows_map_archive_results_by_index(client):
    data = client.post("/api/v1/resolve/batch", json={
        "purls": ["not-a-purl", PURL], "find_source_archive": True,
    }).json()
    results = data["results"]
    assert results[0]["error"] == "invalid_purl"
    assert results[0]["source_archive_url"] is None
    assert results[1]["error"] is None
    assert results[1]["source_archive_match"] == "exact"


def test_flag_on_returns_commit_metadata(client):
    item = client.post("/api/v1/resolve/batch", json={
        "purls": [PURL], "find_source_archive": True,
    }).json()["results"][0]
    assert item["source_archive_commit_sha"] == TAG_SHA
    assert item["source_archive_commit_url"].endswith(f"/archive/{TAG_SHA}.tar.gz")
    assert item["source_archive_ref_type"] == "tag"
    assert item["source_archive_matched_version"] == "23.8.16.40"
    assert item["source_archive_resolver"] == "git-tags"
    assert item["source_archive_resolved_at"]
