from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from purl_resolver.resolver.depsdev import DepsdevResolver
from purl_resolver.resolver.retry import RetryConfig

_API_BASE = "https://api.deps.dev/v3"

_MAVEN_NAME = "org.glassfish.jaxb%3Ajaxb-core"


def make_resolver() -> tuple[DepsdevResolver, AsyncMock]:
    get = AsyncMock()
    client = MagicMock()
    client.get = get
    resolver = DepsdevResolver(timeout=5.0, retry_config=RetryConfig(max_attempts=1))
    resolver._client = client
    resolver._min_interval = 0
    return resolver, get


def http_response(status_code: int, payload: dict | None = None) -> MagicMock:
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def package_payload(
    versions: list[tuple[str, bool]] | None = None,
) -> dict:
    if versions is None:
        versions = [("1.0.0", False), ("2.3.9", True), ("4.0.5", False)]
    return {
        "packageKey": {"system": "MAVEN", "name": "org.glassfish.jaxb:jaxb-core"},
        "versions": [
            {
                "versionKey": {
                    "system": "MAVEN",
                    "name": "org.glassfish.jaxb:jaxb-core",
                    "version": version,
                },
                "isDefault": is_default,
            }
            for version, is_default in versions
        ],
    }


def version_payload(repo_url: str | None = "https://github.com/glassfish/jaxb") -> dict:
    links: list[dict] = []
    if repo_url is not None:
        links.append({"label": "SOURCE_REPO", "url": repo_url})
    links.append({"label": "HOMEPAGE", "url": "https://glassfish.org/jaxb"})
    return {
        "versionKey": {
            "system": "MAVEN",
            "name": "org.glassfish.jaxb:jaxb-core",
            "version": "2.3.9",
        },
        "links": links,
    }


def test_name_is_depsdev() -> None:
    resolver = DepsdevResolver()
    assert resolver.name == "depsdev"


@pytest.mark.asyncio
async def test_invalid_purl_returns_warning_without_requests() -> None:
    resolver, get = make_resolver()
    result = await resolver.resolve("not-a-purl")
    assert result.repository_url is None
    assert any("Invalid PURL" in w for w in result.warnings)
    get.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_type_returns_warning_without_requests() -> None:
    resolver, get = make_resolver()
    result = await resolver.resolve("pkg:apk/alpine/curl@7.83.0-r0")
    assert result.repository_url is None
    assert any("Unsupported package type" in w for w in result.warnings)
    get.assert_not_awaited()


class TestResolveWithVersion:
    @pytest.mark.asyncio
    async def test_single_request_to_version_endpoint(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [http_response(200, version_payload())]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@4.0.5")
        assert result.repository_url == "https://github.com/glassfish/jaxb"
        get.assert_awaited_once()
        url = get.await_args.args[0]
        assert url == f"{_API_BASE}/systems/MAVEN/packages/{_MAVEN_NAME}/versions/4.0.5"


class TestResolveWithoutVersion:
    @pytest.mark.asyncio
    async def test_two_requests_uses_default_version(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, package_payload()),
            http_response(200, version_payload()),
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        assert result.repository_url == "https://github.com/glassfish/jaxb"
        assert get.await_count == 2
        package_url = get.await_args_list[0].args[0]
        assert package_url == f"{_API_BASE}/systems/MAVEN/packages/{_MAVEN_NAME}"
        version_url = get.await_args_list[1].args[0]
        assert version_url == f"{_API_BASE}/systems/MAVEN/packages/{_MAVEN_NAME}/versions/2.3.9"

    @pytest.mark.asyncio
    async def test_falls_back_to_last_version_without_default(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, package_payload(versions=[("1.0.0", False), ("4.0.5", False)])),
            http_response(200, version_payload()),
        ]
        await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        version_url = get.await_args_list[1].args[0]
        assert version_url.endswith("/versions/4.0.5")

    @pytest.mark.asyncio
    async def test_prefers_newest_published_at_without_default(self) -> None:
        resolver, get = make_resolver()
        payload = {
            "packageKey": {"system": "MAVEN", "name": "org.glassfish.jaxb:jaxb-core"},
            "versions": [
                {
                    "versionKey": {
                        "system": "MAVEN",
                        "name": "org.glassfish.jaxb:jaxb-core",
                        "version": "1.0.0",
                    },
                    "publishedAt": "2020-01-01T00:00:00Z",
                },
                {
                    "versionKey": {
                        "system": "MAVEN",
                        "name": "org.glassfish.jaxb:jaxb-core",
                        "version": "4.0.5",
                    },
                    "publishedAt": "2023-06-01T00:00:00Z",
                },
                {
                    "versionKey": {
                        "system": "MAVEN",
                        "name": "org.glassfish.jaxb:jaxb-core",
                        "version": "2.3.9",
                    },
                    "publishedAt": "2021-03-01T00:00:00Z",
                },
            ],
        }
        get.side_effect = [http_response(200, payload), http_response(200, version_payload())]
        await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        version_url = get.await_args_list[1].args[0]
        assert version_url.endswith("/versions/4.0.5")

    @pytest.mark.asyncio
    async def test_no_versions_returns_warning(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [http_response(200, package_payload(versions=[]))]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        assert result.repository_url is None
        assert any("No versions" in w for w in result.warnings)
        assert get.await_count == 1


class TestLinkExtraction:
    @pytest.mark.asyncio
    async def test_no_source_repo_link_returns_warning(self) -> None:
        resolver, get = make_resolver()
        payload = {
            "versionKey": {"system": "MAVEN", "name": "x:y", "version": "1.0"},
            "links": [{"label": "HOMEPAGE", "url": "https://example.com"}],
        }
        get.side_effect = [http_response(200, payload)]
        result = await resolver.resolve("pkg:maven/x/y@1.0")
        assert result.repository_url is None
        assert any("SOURCE_REPO" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_related_projects_fallback_when_links_missing(self) -> None:
        resolver, get = make_resolver()
        payload = {
            "versionKey": {
                "system": "MAVEN",
                "name": "org.keycloak:keycloak-common",
                "version": "1.0",
            },
            "links": [{"label": "HOMEPAGE", "url": "https://example.com"}],
            "relatedProjects": [
                {
                    "projectKey": {"id": "github.com/keycloak/keycloak"},
                    "relationType": "SOURCE_REPO",
                }
            ],
        }
        get.side_effect = [http_response(200, payload)]
        result = await resolver.resolve("pkg:maven/org.keycloak/keycloak-common@1.0")
        assert result.repository_url == "https://github.com/keycloak/keycloak"


class TestErrors:
    @pytest.mark.asyncio
    async def test_not_found_returns_warning(self) -> None:
        resolver, get = make_resolver()
        response = MagicMock()
        response.status_code = 404
        get.side_effect = httpx.HTTPStatusError("Not Found", request=MagicMock(), response=response)
        result = await resolver.resolve("pkg:maven/org.missing/nonexistent")
        assert result.repository_url is None
        assert any("404" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_network_error_returns_warning(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = httpx.ConnectError("refused")
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        assert result.repository_url is None
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_non_json_response_returns_warning(self) -> None:
        resolver, get = make_resolver()
        response = MagicMock()
        response.status_code = 200
        response.json.side_effect = json.JSONDecodeError("bad", "doc", 0)
        get.side_effect = [response]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url is None
        assert any("invalid response" in w for w in result.warnings)


class TestUrlNormalization:
    @pytest.mark.asyncio
    async def test_http_is_upgraded_to_https(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [http_response(200, version_payload(repo_url="http://github.com/glassfish/jaxb"))]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://github.com/glassfish/jaxb"

    @pytest.mark.asyncio
    async def test_scm_git_prefix_stripped(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [http_response(200, version_payload(repo_url="scm:git:https://github.com/glassfish/jaxb.git"))]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://github.com/glassfish/jaxb"

    @pytest.mark.asyncio
    async def test_git_ssh_style_converted(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="git@github.com:glassfish/jaxb.git"))
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://github.com/glassfish/jaxb"

    @pytest.mark.asyncio
    async def test_git_scheme_converted_to_https(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="git://github.com/jbossas/jboss-invocation"))
        ]
        result = await resolver.resolve("pkg:maven/org.jboss.invocation/jboss-invocation@1.0")
        assert result.repository_url == "https://github.com/jbossas/jboss-invocation"

    @pytest.mark.asyncio
    async def test_ssh_git_colon_converted(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="ssh://git@github.com:glassfish/jaxb.git"))
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://github.com/glassfish/jaxb"

    @pytest.mark.asyncio
    async def test_ssh_real_port_preserved(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="ssh://git@gitlab.com:2222/org/repo.git"))
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://gitlab.com:2222/org/repo"

    @pytest.mark.asyncio
    async def test_gitlab_branch_suffix_stripped(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="https://gitlab.com/group/repo/-/tree/main"))
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url == "https://gitlab.com/group/repo"

    @pytest.mark.asyncio
    async def test_non_https_scheme_is_rejected(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="javascript:alert(1)"))
        ]
        result = await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core@1.0")
        assert result.repository_url is None
        assert any("Invalid repository URL" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_github_branch_suffix_stripped(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, version_payload(repo_url="https://github.com/keycloak/keycloak/tree/master"))
        ]
        result = await resolver.resolve("pkg:maven/org.keycloak/keycloak-account-ui@1.0")
        assert result.repository_url == "https://github.com/keycloak/keycloak"


class TestNameMapping:
    @pytest.mark.asyncio
    async def test_npm_scoped_package_name_is_encoded(self) -> None:
        resolver, get = make_resolver()
        payload = {
            "versionKey": {"system": "NPM", "name": "@colors/colors", "version": "1.5.0"},
            "links": [{"label": "SOURCE_REPO", "url": "https://github.com/DABH/colors.js"}],
        }
        get.side_effect = [http_response(200, payload)]
        result = await resolver.resolve("pkg:npm/%40colors/colors@1.5.0")
        assert result.repository_url == "https://github.com/DABH/colors.js"
        url = get.await_args.args[0]
        assert url == f"{_API_BASE}/systems/NPM/packages/%40colors%2Fcolors/versions/1.5.0"

    @pytest.mark.asyncio
    async def test_maven_name_contains_colon_separator(self) -> None:
        resolver, get = make_resolver()
        get.side_effect = [
            http_response(200, package_payload()),
            http_response(200, version_payload()),
        ]
        await resolver.resolve("pkg:maven/org.glassfish.jaxb/jaxb-core")
        url = get.await_args_list[0].args[0]
        assert url == f"{_API_BASE}/systems/MAVEN/packages/{_MAVEN_NAME}"


class TestFactory:
    def test_depsdev_is_second_in_chain(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            apk_resolver_enabled=False,
        )
        resolvers = build_resolvers(Settings(), app_settings)
        assert resolvers[0].name == "purl2repo"
        assert resolvers[1].name == "depsdev"

    def test_depsdev_not_added_when_disabled(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            depsdev_enabled=False,
            ecosystems_enabled=False,
            librariesio_enabled=False,
            apk_resolver_enabled=False,
        )
        resolvers = build_resolvers(Settings(), app_settings)
        assert all(r.name != "depsdev" for r in resolvers)

    def test_chain_order_with_all_resolvers(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=True,
            librariesio_enabled=True,
            librariesio_api_key="key",
            apk_resolver_enabled=True,
            llm_resolver_enabled=True,
            llm_resolver_base_url="https://api.example.com",
            llm_resolver_api_key="key",
            llm_resolver_model="model",
        )
        resolvers = build_resolvers(Settings(), app_settings)
        names = [r.name for r in resolvers]
        assert names == ["purl2repo", "depsdev", "ecosyste.ms", "libraries.io", "apk", "llm"]
