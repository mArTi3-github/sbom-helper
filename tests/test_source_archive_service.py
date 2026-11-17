import asyncio

import pytest

from purl_resolver.settings_store import AppSettings, SettingsStore
from purl_resolver.source_archive.matching import TagInfo
from purl_resolver.source_archive.service import SourceArchiveService
from purl_resolver.storage.inmemory_source_archive import InMemorySourceArchiveStorage

PURL = "pkg:github/ClickHouse/ClickHouse@23.8.16.40"
REPO = "https://github.com/ClickHouse/ClickHouse"
TAG_SHA = "e143a9039ba36ad0c25f2ed85503f36e88f61063"
OTHER_SHA = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
TAGS = [TagInfo("v23.8.16.40-lts", TAG_SHA), TagInfo("v23.8.16.39", OTHER_SHA)]


def make_service(tmp_path, tags=TAGS, head=True):
    calls = {"tags": 0, "head": 0}

    async def fetcher(url, timeout):
        calls["tags"] += 1
        return list(tags)

    async def checker(url, timeout):
        calls["head"] += 1
        return head

    store = SettingsStore(path=tmp_path / "settings.json")
    service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=store,
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    return service, calls


@pytest.mark.asyncio
async def test_exact_match_is_stored_and_returned(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "exact"
    assert result.archive_url == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/v23.8.16.40-lts.tar.gz"
    )
    assert result.archive_url_commit == (
        f"https://github.com/ClickHouse/ClickHouse/archive/{TAG_SHA}.tar.gz"
    )
    assert result.matched_ref == "v23.8.16.40-lts"
    assert result.resolver == "git-tags"
    assert calls["tags"] == 1


@pytest.mark.asyncio
async def test_exact_match_without_commit_sha_has_no_commit_url(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v23.8.16.40-lts")])
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "exact"
    assert result.archive_url == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/v23.8.16.40-lts.tar.gz"
    )
    assert result.archive_url_commit is None


@pytest.mark.asyncio
async def test_multiple_exact_tags_add_warning(tmp_path) -> None:
    service, _ = make_service(
        tmp_path,
        tags=[
            TagInfo("v1.2.3", "0f1e2d3c4b5a69788796a5b4c3d2e1f001122334"),
            TagInfo("1.2.3", "9a8b7c6d5e4f30211203f4e5d6c7b8a990817263"),
        ],
    )
    result = await service.lookup("pkg:github/a/b@1.2.3", "https://github.com/a/b")
    assert result.matched_ref == "1.2.3"
    assert any("multiple" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_second_lookup_uses_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    result = await service.lookup(PURL, REPO)
    assert result.cached is True
    assert calls["tags"] == 1


@pytest.mark.asyncio
async def test_changed_repository_url_invalidates_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    await service.lookup(PURL, "https://github.com/Other/Repo")
    assert calls["tags"] == 2


@pytest.mark.asyncio
async def test_no_version_returns_no_version_without_fetch(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    result = await service.lookup("pkg:github/ClickHouse/ClickHouse", REPO)
    assert result.match_type == "no_version"
    assert result.reason == "no_version"
    assert calls["tags"] == 0


@pytest.mark.asyncio
async def test_non_numeric_version(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup("pkg:github/a/b@main", "https://github.com/a/b")
    assert result.match_type == "repository_only"
    assert result.reason == "non_numeric_version"


@pytest.mark.asyncio
async def test_missing_repository_is_not_found(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup(PURL, None)
    assert result.match_type == "not_found"
    assert result.reason == "no_repository"


@pytest.mark.asyncio
async def test_non_github_repository(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup(PURL, "https://gitlab.com/a/b")
    assert result.match_type == "repository_only"
    assert result.reason == "unsupported_host"


@pytest.mark.asyncio
async def test_git_error_falls_back_to_repository_only(tmp_path) -> None:
    async def failing_fetcher(url, timeout):
        raise RuntimeError("boom")

    async def ok_checker(url, timeout):
        return True

    service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=SettingsStore(path=tmp_path / "settings.json"),
        tag_fetcher=failing_fetcher,
        url_checker=ok_checker,
    )
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "git_error"


@pytest.mark.asyncio
async def test_near_match_when_no_exact(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v23.8.16.39", OTHER_SHA)])
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "near"
    assert result.matched_version == "23.8.16.39"


@pytest.mark.asyncio
async def test_no_matching_tag(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v1.0.0", OTHER_SHA)])
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "no_matching_tag"


@pytest.mark.asyncio
async def test_head_failure_falls_back_to_repository_only(tmp_path) -> None:
    service, _ = make_service(tmp_path, head=False)
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "archive_check_failed"


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    await service.lookup(PURL, REPO, force_refresh=True)
    assert calls["tags"] == 2


@pytest.mark.asyncio
async def test_storage_failure_does_not_break_result(tmp_path) -> None:
    class FailingStorage(InMemorySourceArchiveStorage):
        async def store_archive(self, row):
            raise RuntimeError("db down")

        async def lookup_archive(self, purl):
            return None

    async def fetcher(url, timeout):
        return list(TAGS)

    async def checker(url, timeout):
        return True

    service = SourceArchiveService(
        storage=FailingStorage(),
        settings_store=SettingsStore(path=tmp_path / "settings.json"),
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "exact"


def make_batch_service(tmp_path, concurrency=5):
    calls = {"tags": 0}
    active = {"current": 0, "max": 0}

    async def fetcher(url, timeout):
        calls["tags"] += 1
        active["current"] += 1
        active["max"] = max(active["max"], active["current"])
        await asyncio.sleep(0.01)
        active["current"] -= 1
        return [TagInfo("v1.0.0", TAG_SHA)]

    async def checker(url, timeout):
        return True

    store = SettingsStore(path=tmp_path / "settings.json")
    store.save(AppSettings(source_archive_concurrency=concurrency))
    service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=store,
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    return service, calls, active


@pytest.mark.asyncio
async def test_enrich_many_preserves_input_order(tmp_path) -> None:
    service, _, _ = make_batch_service(tmp_path)
    results = await service.enrich_many(
        ["pkg:github/a/b@1.0.0", "pkg:github/c/d@2.0.0"],
        ["https://github.com/a/b", "https://github.com/c/d"],
    )
    assert [result.purl for result in results] == [
        "pkg:github/a/b@1.0.0",
        "pkg:github/c/d@2.0.0",
    ]


@pytest.mark.asyncio
async def test_enrich_many_deduplicates_identical_pairs(tmp_path) -> None:
    service, calls, _ = make_batch_service(tmp_path)
    results = await service.enrich_many(
        ["pkg:github/a/b@1.0.0", "pkg:github/a/b@1.0.0"],
        ["https://github.com/a/b", "https://github.com/a/b"],
    )
    assert len(results) == 2
    assert results[0].purl == results[1].purl
    assert calls["tags"] == 1


@pytest.mark.asyncio
async def test_enrich_many_bounds_concurrency(tmp_path) -> None:
    service, _, active = make_batch_service(tmp_path, concurrency=1)
    await service.enrich_many(
        ["pkg:github/a/b@1.0.0", "pkg:github/c/d@2.0.0", "pkg:github/e/f@3.0.0"],
        [
            "https://github.com/a/b",
            "https://github.com/c/d",
            "https://github.com/e/f",
        ],
    )
    assert active["max"] == 1
