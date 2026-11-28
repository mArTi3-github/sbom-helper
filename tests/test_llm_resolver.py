from __future__ import annotations

import json
import ssl
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from openai import APIConnectionError, APIError

from purl_resolver.resolver.llm import LlmResolver, _build_ssl_verify

_BASE_URL = "https://api.example.com"
_API_KEY = "test-key"
_MODEL = "test-model"
_PURL = "pkg:pypi/requests@2.31.0"

_TEST_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIDBTCCAe2gAwIBAgIUOVjTn3UjbzM9+V12JP+mDSIYdMQwDQYJKoZIhvcNAQEL
BQAwEjEQMA4GA1UEAwwHdGVzdC1jYTAeFw0yNjExMjgxMTU4NDJaFw0zNjExMjUx
MTU4NDJaMBIxEDAOBgNVBAMMB3Rlc3QtY2EwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDAHmd2osRANdzgT1lPITOKQYLsMwFhiXytRMrkWhJcQSTiRNdC
8xIBiIl+rWbWyHDRxM+ERGg1jfHO/jjDKw6mf+KsRVuGSnfqjKgS8OojpuYDbHWb
ohZbkkcF9FhriC6L13OcFp6Qo+DjVHrJf16dUe0/QP0rfDVuFBmqRLwER+7VEW3E
Lel9SOyoKOeaxhCdJ2CRUaYUR4Ms1tad50esiNb8CwzFe6Xsoxk6ATYOUD45Cjh6
kg6x0ZhZntxNv6TKC7cr2pzEy6FuDEWv8CQQlDjUVEhpJhmJOZcJdl0bp97Ob5yT
SFeDnmscYOIci+cjnyS8ydKdV+3UwPHhvRIDAgMBAAGjUzBRMB0GA1UdDgQWBBS3
XwBW8V5ArDAYofilBYnsua+/9TAfBgNVHSMEGDAWgBS3XwBW8V5ArDAYofilBYns
ua+/9TAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAJUH6ncrcw
IIrPLpAo/UXcr2dIs+cf4b4JtvNfuM0Q5My5xUOMwo387xcX6HH2bjuBbP/2YHja
oKdG2NAxBaMRhvvhQqkY63Y19C5r3wVT/fyC3pmcvtXg4p0nSW77v9t1N6Kj6SPY
cm+s5F8Xzj9I5v9U8lzksKmXh0r98CVhTalHI6bq2hBaaAlBQWdSj7/s7oxDG2/i
QhTdJzTKWSEjupIgo6neGUKsE+2ti7BE5RG4qinRlTDEkIStxAAizk3L75PO3FQV
eoFy088URbNmOBq/FilIrFyGfnKXY/FFjhdGMD6d+NhkqOomY2ttcrUXrwvyYHd7
ISDO4sIiueAz
-----END CERTIFICATE-----
"""


def make_completion(content: str) -> MagicMock:
    message = MagicMock()
    message.content = content
    message.tool_calls = None
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
        bad = json.dumps(
            {
                "purl": "pkg:pypi/other",
                "status": "success",
                "repository_url": "https://github.com/x",
            }
        )
        set_response(create, [bad, success_json("pkg:pypi/requests@2.31.0")])
        result = await resolver.resolve("pkg:pypi/requests@2.31.0")
        assert result.repository_url == "https://github.com/psf/requests"
        assert create.await_count == 2

    @pytest.mark.asyncio
    async def test_purl_mismatch_exhausts_attempts(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=2)
        bad = json.dumps(
            {
                "purl": "pkg:pypi/other",
                "status": "success",
                "repository_url": "https://github.com/x",
            }
        )
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
        content = json.dumps(
            {"purl": _PURL, "status": "maybe", "repository_url": "https://github.com/x"}
        )
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

    def test_factory_passes_tls_settings(self) -> None:
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
            llm_resolver_verify_ssl=False,
            llm_resolver_ca_bundle="/etc/ssl/corp-ca.pem",
        )
        with patch("purl_resolver.resolver.factory.LlmResolver") as llm_cls:
            llm_cls.return_value.name = "llm"
            build_resolvers(Settings(), app_settings)
        kwargs = llm_cls.call_args.kwargs
        assert kwargs["verify_ssl"] is False
        assert kwargs["ca_bundle"] == "/etc/ssl/corp-ca.pem"

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


class TestTlsConfiguration:
    def test_default_verification_is_true(self) -> None:
        assert _build_ssl_verify(True, None) is True

    def test_verify_disabled_returns_cert_none_context(self) -> None:
        ctx = _build_ssl_verify(False, None)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_verify_disabled_ignores_ca_bundle(self) -> None:
        ctx = _build_ssl_verify(False, "/etc/ssl/corp-ca.pem")
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_empty_ca_bundle_is_unset(self) -> None:
        assert _build_ssl_verify(True, "") is True

    def test_ca_bundle_loaded_returns_context(self, tmp_path) -> None:
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text(_TEST_CA_PEM)
        ctx = _build_ssl_verify(True, str(ca_file))
        assert isinstance(ctx, ssl.SSLContext)
        assert len(ctx.get_ca_certs()) >= 1

    def test_missing_ca_bundle_falls_back_and_warns(self, caplog: pytest.LogCaptureFixture) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="purl_resolver.resolver.llm"):
            assert _build_ssl_verify(True, "/nonexistent/ca.pem") is True
        assert any("CA bundle" in m for m in caplog.messages)

    def test_client_created_with_max_retries_zero(self) -> None:
        with patch("purl_resolver.resolver.llm.AsyncOpenAI") as client_cls:
            LlmResolver(base_url=_BASE_URL, api_key=_API_KEY, model=_MODEL)
        kwargs = client_cls.call_args.kwargs
        assert kwargs["max_retries"] == 0
        assert "http_client" in kwargs

    @pytest.mark.asyncio
    async def test_connection_error_reason_surfaces_in_warnings(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        err = APIConnectionError(request=MagicMock(), message="Connection error.")
        err.__cause__ = httpx.ConnectError(
            "CERTIFICATE_VERIFY_FAILED self-signed certificate"
        )
        create.side_effect = err
        result = await resolver.resolve(_PURL)
        assert result.repository_url is None
        assert any("CERTIFICATE_VERIFY_FAILED" in w for w in result.warnings)
        assert any("ConnectError" in w for w in result.warnings)


def make_tool_call_completion(tool_name: str, arguments: str, call_id: str = "call_1") -> MagicMock:
    call = MagicMock()
    call.id = call_id
    call.function.name = tool_name
    call.function.arguments = arguments
    message = MagicMock()
    message.content = None
    message.tool_calls = [call]
    choice = MagicMock()
    choice.message = message
    completion = MagicMock()
    completion.choices = [choice]
    return completion


class TestToolCallingLoop:
    @pytest.mark.asyncio
    async def test_tools_passed_to_create(self) -> None:
        resolver, create, _ = make_llm_resolver()
        set_response(create, [success_json(_PURL)])
        await resolver.resolve(_PURL)
        tools = create.await_args.kwargs["tools"]
        assert {tool["function"]["name"] for tool in tools} == {"web_search", "web_fetch"}

    @pytest.mark.asyncio
    async def test_tool_call_executed_then_final_answer(self) -> None:
        resolver, create, _ = make_llm_resolver()
        resolver._web_search = AsyncMock(return_value="result-text")  # type: ignore
        create.side_effect = [
            make_tool_call_completion("web_search", '{"query": "requests repo"}'),
            make_completion(success_json(_PURL)),
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url == "https://github.com/psf/requests"
        resolver._web_search.assert_awaited_once_with("requests repo")
        second_messages = create.await_args_list[1].kwargs["messages"]
        assert any(
            m.get("role") == "tool" and m.get("content") == "result-text" for m in second_messages
        )

    @pytest.mark.asyncio
    async def test_tool_round_exhaustion_is_terminal(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=3)
        resolver._web_search = AsyncMock(return_value="x")  # type: ignore
        create.side_effect = [
            make_tool_call_completion("web_search", '{"query": "a"}')
            for _ in range(resolver._max_tool_rounds + 1)
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url is None
        assert any("max tool rounds" in w for w in result.warnings)
        assert create.await_count == resolver._max_tool_rounds + 1

    @pytest.mark.asyncio
    async def test_invalid_tool_arguments_return_error_string(self) -> None:
        resolver, create, _ = make_llm_resolver()
        create.side_effect = [
            make_tool_call_completion("web_search", "not-json"),
            make_completion(success_json(_PURL)),
        ]
        result = await resolver.resolve(_PURL)
        assert result.repository_url == "https://github.com/psf/requests"
        second_messages = create.await_args_list[1].kwargs["messages"]
        assert any(
            m.get("role") == "tool" and str(m.get("content", "")).startswith("error:")
            for m in second_messages
        )
