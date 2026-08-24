from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from openai import APIError

from purl_resolver.resolver.llm import LlmResolver

_BASE_URL = "https://api.example.com"
_API_KEY = "test-key"
_MODEL = "test-model"
_PURL = "pkg:pypi/requests@2.31.0"


def make_completion(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


def make_llm_resolver(
    *,
    attempts_count: int = 2,
    status_codes: list[int] | None = None,
) -> tuple[LlmResolver, AsyncMock, AsyncMock]:
    create = AsyncMock()
    chat = MagicMock()
    chat.completions.create = create
    client = MagicMock()
    client.chat = chat

    head = AsyncMock()
    if status_codes is None:
        status_codes = [200]
    responses = [MagicMock(status_code=code) for code in status_codes]
    head.side_effect = responses

    resolver = LlmResolver(
        base_url=_BASE_URL,
        api_key=_API_KEY,
        model=_MODEL,
        attempts_count=attempts_count,
    )
    resolver._client = client
    resolver._http_client = MagicMock()
    resolver._http_client.head = head
    return resolver, create, head


def set_response(create: AsyncMock, contents: list[str]) -> None:
    create.side_effect = [make_completion(content) for content in contents]


def api_error(message: str) -> APIError:
    return APIError(message, request=MagicMock(), body=None)


def success_json(purl: str, repo_url: str = "https://github.com/psf/requests") -> str:
    return json.dumps({"purl": purl, "status": "success", "repository_url": repo_url})


class TestResolverName:
    def test_name_is_llm(self) -> None:
        resolver, _, _ = make_llm_resolver()
        assert resolver.name == "llm"


class TestInvalidPurl:
    @pytest.mark.asyncio
    async def test_invalid_purl_returns_warning_without_llm_call(self) -> None:
        resolver, create, _ = make_llm_resolver()
        result = await resolver.resolve("not-a-purl")
        assert result.repository_url is None
        assert any("Invalid PURL" in w for w in result.warnings)
        create.assert_not_awaited()


class TestResolveSuccess:
    @pytest.mark.asyncio
    async def test_successful_resolution(self) -> None:
        resolver, create, _ = make_llm_resolver()
        set_response(create, [success_json("pkg:pypi/requests@2.31.0")])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_json_extracted_from_code_fence(self) -> None:
        resolver, create, _ = make_llm_resolver()
        content = "```json\n" + success_json("pkg:pypi/requests@2.31.0") + "\n```"
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_extra_text_around_json_is_tolerated(self) -> None:
        resolver, create, _ = make_llm_resolver()
        content = "Here is the answer:\n" + success_json("pkg:pypi/requests@2.31.0")
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"


class TestResponseValidation:
    @pytest.mark.asyncio
    async def test_non_json_response_exhausts_attempts(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        set_response(create, ["hello there", "still not json"])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert create.await_count == 2
        assert any("JSON" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_purl_mismatch_retries_and_succeeds(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        bad = json.dumps({"purl": "pkg:pypi/other", "status": "success", "repository_url": "https://github.com/x"})
        set_response(create, [bad, success_json("pkg:pypi/requests@2.31.0")])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2

    @pytest.mark.asyncio
    async def test_purl_mismatch_exhausts_attempts(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        bad = json.dumps({"purl": "pkg:pypi/other", "status": "success", "repository_url": "https://github.com/x"})
        set_response(create, [bad, bad])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert any("purl" in w.lower() for w in result.warnings)

    @pytest.mark.asyncio
    async def test_status_failure_returns_no_repository(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        content = json.dumps({"purl": _PURL, "status": "failure", "repository_url": None})
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert len(result.warnings) > 0

    @pytest.mark.asyncio
    async def test_invalid_status_value_is_rejected(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        content = json.dumps({"purl": _PURL, "status": "maybe", "repository_url": "https://github.com/x"})
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None

    @pytest.mark.asyncio
    async def test_invalid_repository_url_format_is_rejected(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        content = json.dumps({"purl": _PURL, "status": "success", "repository_url": "not-a-url"})
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert any("repository_url" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_missing_repository_url_is_rejected(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        content = json.dumps({"purl": _PURL, "status": "success"})
        set_response(create, [content])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None


class TestHeadCheck:
    @pytest.mark.asyncio
    async def test_head_failure_retries_with_feedback(self) -> None:
        resolver, create, head = make_llm_resolver(attempts_count=2, status_codes=[404, 200])
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2
        assert head.await_count == 2

    @pytest.mark.asyncio
    async def test_head_failure_exhausts_attempts(self) -> None:
        resolver, create, head = make_llm_resolver(attempts_count=2, status_codes=[404, 500])
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert any("404" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_head_network_error_counts_as_failed_attempt(self) -> None:
        resolver, create, head = make_llm_resolver(attempts_count=2)
        head.side_effect = [httpx.ConnectError("refused"), httpx.ConnectError("refused")]
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert create.await_count == 2


class TestApiErrors:
    @pytest.mark.asyncio
    async def test_api_error_retries_and_succeeds(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        create.side_effect = [api_error("boom"), make_completion(success_json(_PURL))]
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2

    @pytest.mark.asyncio
    async def test_api_error_exhausts_attempts(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        create.side_effect = [api_error("boom"), api_error("boom again")]
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None
        assert create.await_count == 2
        assert any("LLM request failed" in w for w in result.warnings)

    @pytest.mark.asyncio
    async def test_httpx_error_counts_as_failed_attempt(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        create.side_effect = httpx.ConnectError("refused")
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url is None


class TestPrompt:
    @pytest.mark.asyncio
    async def test_prompt_contains_purl_and_json_format(self) -> None:
        resolver, create, _ = make_llm_resolver()
        set_response(create, [success_json("pkg:pypi/requests@2.31.0")])
        await resolver.resolve("pkg:pypi/requests@2.31.0")
        kwargs = create.await_args.kwargs
        assert kwargs["model"] == _MODEL
        messages = kwargs["messages"]
        assert any("pkg:pypi/requests@2.31.0" in str(m["content"]) for m in messages)
        assert any("repository_url" in str(m["content"]) for m in messages)


class TestLogging:
    @pytest.mark.asyncio
    async def test_attempts_are_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        resolver, create, _ = make_llm_resolver(attempts_count=2, status_codes=[404, 200])
        set_response(create, [success_json(_PURL), success_json(_PURL)])
        with caplog.at_level(logging.INFO, logger="purl_resolver.resolver.llm"):
            await resolver.resolve(_PURL)
        assert any("attempt 1/2" in m for m in caplog.messages)
        assert any("attempt 2/2" in m for m in caplog.messages)

    @pytest.mark.asyncio
    async def test_failure_reason_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        set_response(create, ["not json at all"])
        with caplog.at_level(logging.WARNING, logger="purl_resolver.resolver.llm"):
            await resolver.resolve(_PURL)
        assert any("failed" in m for m in caplog.messages)
        assert any("JSON" in m for m in caplog.messages)


class TestFactory:
    def test_llm_resolver_is_last_in_chain(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            llm_resolver_enabled=True,
            llm_resolver_base_url=_BASE_URL,
            llm_resolver_api_key=_API_KEY,
            llm_resolver_model=_MODEL,
        )
        resolvers = build_resolvers(Settings(), app_settings)
        assert resolvers[-1].name == "llm"

    def test_llm_resolver_not_added_when_disabled(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            llm_resolver_enabled=False,
            llm_resolver_base_url=_BASE_URL,
            llm_resolver_api_key=_API_KEY,
            llm_resolver_model=_MODEL,
        )
        resolvers = build_resolvers(Settings(), app_settings)
        assert all(r.name != "llm" for r in resolvers)

    def test_llm_resolver_not_added_without_credentials(self) -> None:
        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            llm_resolver_enabled=True,
        )
        resolvers = build_resolvers(Settings(), app_settings)
        assert all(r.name != "llm" for r in resolvers)

    def test_missing_credentials_log_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            llm_resolver_enabled=True,
            llm_resolver_base_url=_BASE_URL,
            llm_resolver_model=_MODEL,
        )
        with caplog.at_level(logging.WARNING, logger="purl_resolver.resolver.factory"):
            build_resolvers(Settings(), app_settings)
        assert any("LLM resolver is enabled but not added" in m for m in caplog.messages)
        assert any("llm_resolver_api_key" in m for m in caplog.messages)

    def test_fully_configured_logs_info(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        from purl_resolver.config import Settings
        from purl_resolver.resolver.factory import build_resolvers
        from purl_resolver.settings_store import AppSettings

        app_settings = AppSettings(
            ecosystems_enabled=False,
            librariesio_enabled=False,
            llm_resolver_enabled=True,
            llm_resolver_base_url=_BASE_URL,
            llm_resolver_api_key=_API_KEY,
            llm_resolver_model=_MODEL,
        )
        with caplog.at_level(logging.INFO, logger="purl_resolver.resolver.factory"):
            build_resolvers(Settings(), app_settings)
        assert any("LLM resolver added as the last resolver" in m for m in caplog.messages)
