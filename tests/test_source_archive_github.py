import httpx
import pytest

from purl_resolver.source_archive.github import (
    GitHubRepo,
    check_archive_url,
    commit_archive_url,
    parse_github_repository,
    tag_archive_url,
)


def test_parse_github_repository_variants() -> None:
    assert parse_github_repository("https://github.com/ClickHouse/ClickHouse.git") == GitHubRepo(
        "ClickHouse", "ClickHouse"
    )
    assert parse_github_repository("https://www.github.com/psf/requests/") == GitHubRepo(
        "psf", "requests"
    )


def test_parse_github_repository_rejects_other_hosts_and_extra_paths() -> None:
    assert parse_github_repository("https://gitlab.com/a/b") is None
    assert parse_github_repository("https://github.com/a/b/tree/main") is None


def test_archive_urls() -> None:
    repo = GitHubRepo("ClickHouse", "ClickHouse")
    assert tag_archive_url(repo, "v23.8.16.40-lts") == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/v23.8.16.40-lts.tar.gz"
    )
    assert tag_archive_url(repo, "release/1.2.3") == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/release/1.2.3.tar.gz"
    )
    assert commit_archive_url(repo, "e143a9039ba36ad0c25f2ed85503f36e88f61063") == (
        "https://github.com/ClickHouse/ClickHouse/archive/e143a9039ba36ad0c25f2ed85503f36e88f61063.tar.gz"
    )


@pytest.mark.asyncio
async def test_check_archive_url_follows_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "github.com":
            return httpx.Response(
                302, headers={"location": "https://codeload.github.com/x/y/tar.gz/abc"}
            )
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        assert await check_archive_url(
            "https://github.com/x/y/archive/abc.tar.gz", 5, client=client
        )


@pytest.mark.asyncio
async def test_check_archive_url_returns_false_on_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        assert not await check_archive_url(
            "https://github.com/x/y/archive/abc.tar.gz", 5, client=client
        )
