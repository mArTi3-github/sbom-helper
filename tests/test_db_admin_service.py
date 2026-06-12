from __future__ import annotations

import pytest

from purl_resolver.db_admin_service import DbAdminService
from purl_resolver.schemas import ImportStrategy, PurlListParams, PurlUpdateRequest, ResolveResponse
from purl_resolver.storage.inmemory import InMemoryCache


@pytest.fixture
def storage():
    return InMemoryCache()


@pytest.fixture
def service(storage):
    return DbAdminService(storage)


@pytest.fixture
def populated_storage(storage):
    entries = [
        ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            repository_type="github",
            repository_kind="source_code",
            confidence="high",
        ),
        ResolveResponse(
            purl="pkg:npm/express",
            repository_url="https://github.com/expressjs/express",
            repository_type="github",
            repository_kind="source_code",
            confidence="low",
        ),
    ]
    for e in entries:
        storage._store[e.purl] = e
    return storage


class TestDbAdminServiceList:
    @pytest.mark.asyncio
    async def test_list_empty(self, service):
        params = PurlListParams()
        result = await service.list_purls(params)
        assert result.total == 0
        assert result.rows == []

    @pytest.mark.asyncio
    async def test_list_with_data(self, populated_storage, service):
        params = PurlListParams()
        result = await service.list_purls(params)
        assert result.total == 2
        assert len(result.rows) == 2

    @pytest.mark.asyncio
    async def test_list_search(self, populated_storage, service):
        params = PurlListParams(search="requests")
        result = await service.list_purls(params)
        assert result.total == 1
        assert result.rows[0].purl == "pkg:pypi/requests"

    @pytest.mark.asyncio
    async def test_list_pagination(self, populated_storage, service):
        params = PurlListParams(page=1, page_size=1)
        result = await service.list_purls(params)
        assert len(result.rows) == 1
        assert result.total == 2
        assert result.page == 1
        assert result.page_size == 1


class TestDbAdminServiceUpdate:
    @pytest.mark.asyncio
    async def test_update_repository_url(self, populated_storage, service):
        body = PurlUpdateRequest(repository_url="https://github.com/psf/requests-v3")
        ok, err = await service.update_purl("pkg:pypi/requests", body)
        assert ok is True
        assert err is None
        cached = populated_storage._store["pkg:pypi/requests"]
        assert cached.repository_url == "https://github.com/psf/requests-v3"

    @pytest.mark.asyncio
    async def test_update_rekey(self, populated_storage, service):
        body = PurlUpdateRequest(purl="pkg:pypi/requests3", repository_url="https://github.com/psf/requests3")
        ok, err = await service.update_purl("pkg:pypi/requests", body)
        assert ok is True
        assert "pkg:pypi/requests" not in populated_storage._store
        assert "pkg:pypi/requests3" in populated_storage._store

    @pytest.mark.asyncio
    async def test_update_not_found(self, populated_storage, service):
        body = PurlUpdateRequest(repository_url="https://example.com")
        ok, err = await service.update_purl("pkg:pypi/nonexistent", body)
        assert ok is False
        assert err == "PURL not found"

    @pytest.mark.asyncio
    async def test_update_empty_repo_for_new_row(self, service):
        body = PurlUpdateRequest()
        ok, err = await service.update_purl("pkg:pypi/new", body)
        assert ok is False
        assert err == "repository_url is required for new rows"


class TestDbAdminServiceDelete:
    @pytest.mark.asyncio
    async def test_delete_single(self, populated_storage, service):
        deleted = await service.delete_purls(["pkg:pypi/requests"])
        assert deleted == 1
        assert "pkg:pypi/requests" not in populated_storage._store

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, service):
        deleted = await service.delete_purls(["pkg:pypi/nonexistent"])
        assert deleted == 0


class TestDbAdminServiceImport:
    @pytest.mark.asyncio
    async def test_import_upsert(self, service):
        text = "purl;repository_url\npkg:pypi/newpkg;https://github.com/new/pkg\n"
        result = await service.import_csv(text, ImportStrategy.upsert)
        assert result.imported == 1
        assert result.skipped == 0
        assert result.errors == []

    @pytest.mark.asyncio
    async def test_import_skip_existing(self, populated_storage, service):
        text = (
            "purl;repository_url\n"
            "pkg:pypi/requests;https://github.com/NEW/requests\n"
            "pkg:pypi/totallynew;https://github.com/new/totallynew\n"
        )
        result = await service.import_csv(text, ImportStrategy.skip_existing)
        assert result.imported == 1
        assert result.skipped == 1


class TestDbAdminServiceExport:
    @pytest.mark.asyncio
    async def test_export_empty(self, service):
        params = PurlListParams()
        csv_text = await service.export_csv(params)
        assert "purl;repository_url" in csv_text

    @pytest.mark.asyncio
    async def test_export_with_data(self, populated_storage, service):
        params = PurlListParams()
        csv_text = await service.export_csv(params)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows

    @pytest.mark.asyncio
    async def test_export_with_search(self, populated_storage, service):
        params = PurlListParams(search="requests")
        csv_text = await service.export_csv(params)
        lines = csv_text.strip().split("\n")
        assert len(lines) == 2  # header + 1 row