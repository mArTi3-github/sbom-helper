import pytest

from purl_resolver.storage.inmemory_source_archive import InMemorySourceArchiveStorage
from purl_resolver.storage.source_archive import SourceArchiveRow


def row(purl: str = "pkg:github/a/b@1.2.3", match_type: str = "exact") -> SourceArchiveRow:
    return SourceArchiveRow(
        purl=purl,
        version="1.2.3",
        match_type=match_type,
        archive_url="https://github.com/a/b/archive/refs/tags/v1.2.3.tar.gz",
        matched_ref="v1.2.3",
        matched_ref_type="tag",
        matched_version="1.2.3",
        repository_url="https://github.com/a/b",
        resolver="git-tags",
        resolved_at="2026-11-17T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_store_and_lookup_roundtrip() -> None:
    storage = InMemorySourceArchiveStorage()
    await storage.store_archive(row())
    assert await storage.lookup_archive("pkg:github/a/b@1.2.3") == row()


@pytest.mark.asyncio
async def test_lookup_miss_returns_none() -> None:
    assert await InMemorySourceArchiveStorage().lookup_archive("pkg:github/a/b@9.9.9") is None


@pytest.mark.asyncio
async def test_store_overwrites_existing_purl() -> None:
    storage = InMemorySourceArchiveStorage()
    await storage.store_archive(row(match_type="not_found"))
    await storage.store_archive(row(match_type="exact"))
    stored = await storage.lookup_archive("pkg:github/a/b@1.2.3")
    assert stored.match_type == "exact"
