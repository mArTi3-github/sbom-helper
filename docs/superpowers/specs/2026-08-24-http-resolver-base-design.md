# HTTP Resolver Base Module — Design

## Problem

Four network resolvers (`DepsdevResolver`, `EcosystemsResolver`, `LibrariesIoResolver`, `LlmResolver`) duplicate the same plumbing:

- Each creates its own `httpx.AsyncClient` in `__init__` and **never closes it** (connection leak on settings rebuild and shutdown).
- Rate limiting (`_rate_limit_wait` + `_min_interval`/`_last_request_time`) is copy-pasted in three files (`depsdev.py:192`, `ecosystems.py:102`, `librariesio.py:108`).
- The timeout/status/network → warning error ladder is re-implemented three times with near-identical bodies.
- PURL validation boilerplate (`try: validate(purl) except PurlValidationError → warning Resolution`) is copy-pasted in five files.
- `LlmResolver._check_url` (`llm.py:165`) performs an HTTP HEAD check **without SSRF protection**, while `url_validator._head_request` (`url_validator.py:100`) has it — three separate HEAD implementations exist (`llm.py`, `url_validator.py:_head_request`, `ensure_connectivity`).
- URL normalization exists only in depsdev (`depsdev.py:39`); ecosyste.ms/libraries.io URLs are stored as-is.
- Latent bug: `response.json()` in `ecosystems.py:85` and `librariesio.py:95` is outside the try block — a non-JSON response raises an unhandled `ValueError` and can fail the whole request with 500.

## Solution

Introduce a two-level base-class hierarchy in a new module `src/purl_resolver/resolver/base.py`, plus a shared SSRF-guarded HEAD module `src/purl_resolver/url_check.py`. The four network resolvers become thin adapters carrying only payload logic. The `Resolver` ABC, `Resolution`, chain ordering, and all public constructor signatures of the resolvers stay unchanged.

## Decisions

1. **Two-level hierarchy** (not composition, not plain functions). `HttpResolver` holds the stateless helpers shared by all network resolvers; `HttpApiResolver(HttpResolver)` adds the stateful client/rate-limit/retry machinery used only by the three JSON-API resolvers. `LlmResolver` inherits only `HttpResolver` — it uses the OpenAI SDK for its API call and keeps its own attempts loop, so it must not inherit an unused httpx client, rate limiter, or RetryHelper (avoids dead members of the base class).
2. **`url_check.py` is the single home of SSRF-guarded HEAD logic**, used by both `url_validator.py` (validation of cached URLs) and the resolvers (LLM URL verification). Two consumers = real seam. The resolver layer does not get an import edge to `url_validator`.
3. **URL normalization becomes a chain-wide policy** applied to every resolver that produces a URL: purl2repo, depsdev, ecosystems, librariesio, llm. `normalize_repository_url` is a module-level function in `resolver/base.py`, so `Purl2RepoResolver` (which does not inherit `HttpResolver`) can use it too. Behavioral change: new resolutions store normalized URLs (`https://`, no `.git`, no `/tree/`); existing DB rows are untouched. purl2repo's internal file cache is unaffected — transformation happens at our seam.
4. **Client lifecycle is explicit**: `HttpApiResolver.close()` closes the httpx client; `LlmResolver.close()` closes the `AsyncOpenAI` client. Closing happens via duck-typing (`getattr(resolver, "close", None)`) at settings rebuild (`routes/settings.py::_rebuild_resolvers`) and lifespan teardown (`main.py`). The `Resolver` ABC is not extended.
5. **Two retry regimes stay separate and structurally distinct**: transport retry (`RetryHelper`/`RetryConfig`, shared by the three API resolvers via `HttpApiResolver`) vs. generation retry (LLM attempts loop with `llm_resolver_attempts_count` and prompt feedback). The attempts loop lives only in `LlmResolver.resolve()`; the base classes contain no retry loop. Deterministic resolvers never re-run "analysis" — a failed lookup just falls through to the next resolver in the chain.
6. **Warning message formats are preserved byte-identically** where they exist today (label/subject parametrization), so existing behavior and tests that assert on warning text keep working. The only text change is in llm: an invalid scheme is now reported by normalization (`"not a valid https URL"` instead of `"not a valid http(s) URL"`).

## Architecture

### New file: `src/purl_resolver/url_check.py`

```python
# SSRF guard + HEAD check, shared by url_validator and resolvers

async def is_private_url(url: str) -> bool:
    # moved from url_validator.py:45-62 (DNS resolve + _PRIVATE_NETWORKS)

async def head_url(url: str, timeout: float) -> httpx.Response:
    # SSRF check before request → HEAD (follow_redirects=True)
    # → re-check final URL; raises ConnectionError on private address
    # semantics moved from url_validator.py:100-107
```

`url_validator.py` is refactored to use these: local `_is_private_url`/`_PRIVATE_NETWORKS`/`_head_request` bodies are removed, `ensure_connectivity` keeps its own HEAD semantics (no redirects, `status < 500`) but uses `url_check.is_private_url`. Public exports of `url_validator` (`validate_url`, `ensure_connectivity`, `UrlValidationResult`, `UrlValidationOutput`) are unchanged.

### New file: `src/purl_resolver/resolver/base.py`

```python
def normalize_repository_url(url: str) -> str | None:
    # module-level function, moved from depsdev.py:39-81 — chain-wide policy;
    # callable by HttpResolver subclasses and by Purl2RepoResolver (non-inheritor)

class HttpResolver(Resolver):
    def __init__(self, *, timeout: float = 15.0) -> None:
        self._timeout = timeout

    @staticmethod
    def _validate_purl(purl: str) -> tuple[PurlComponents | None, str | None]:
        # returns (components, None) or (None, "Invalid PURL: {e}")

    async def _check_url(self, url: str) -> tuple[bool, str]:
        # delegates to url_check.head_url with self._timeout
        # (True, "") on success; (False, reason) on ConnectionError
        # (private IP), httpx error, or status >= 400
        # message formats preserved from llm.py:165-172


class HttpApiResolver(HttpResolver):
    def __init__(
        self,
        *,
        timeout: float = 15.0,
        max_requests_per_second: float = 0.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        super().__init__(timeout=timeout)
        self._client = httpx.AsyncClient(timeout=timeout)
        self._min_interval = 1.0 / max_requests_per_second if max_requests_per_second > 0 else 0
        self._last_request_time = 0.0
        self._retry = RetryHelper(retry_config or RetryConfig())

    async def _rate_limit_wait(self) -> None:
        # unified from depsdev.py:192 / ecosystems.py:102 / librariesio.py:108

    async def _get_json(
        self, purl: str, url: str, *, label: str,
        params: dict | None = None, subject: str | None = None,
    ) -> tuple[dict | None, str | None]:
        # rate-limit → RetryHelper → raise_for_status → json
        # error ladder, formats preserved:
        #   "{label} error {status} for {subject}"
        #   "{label} timeout for {subject}"
        #   "{label} network error for {subject}: {exc}"
        #   "{label} invalid response for {subject}"  (ValueError — fixes latent 500)

    async def close(self) -> None:
        await self._client.aclose()
```

Attribute names `_client`, `_min_interval`, `_last_request_time` are preserved exactly — existing tests replace/mock them directly.

### Modified: `src/purl_resolver/resolver/depsdev.py`

- `class DepsdevResolver(HttpApiResolver)`; constructor signature unchanged `(timeout=15.0, max_requests_per_second=1.0, retry_config=None)` → forwarded to `super().__init__()`.
- Keeps: `_SYSTEMS`, `build_package_name`, `extract_source_repo_url`, version-selection logic.
- Keeps re-export `from .base import normalize_repository_url` so `purl_resolver.resolver.depsdev.normalize_repository_url` still resolves.
- `resolve()`: `_validate_purl` → version selection → `_get_json(purl, version_url, label="deps.dev")` → `extract_source_repo_url` → `self.normalize_repository_url(...)` → `Resolution`.
- Removes: private `_get_json`, `_rate_limit_wait`, unused imports.

### Modified: `src/purl_resolver/resolver/ecosystems.py`

- `class EcosystemsResolver(HttpApiResolver)`; constructor `(api_key=None, timeout=15.0, max_requests_per_second=2.0, retry_config=None)`.
- Keeps: `_API_URL`, `select_repository_url`.
- `resolve()`: `_validate_purl` → params (api_key) → `_get_json(purl, _API_URL, label="ecosyste.ms", params=params)` → non-empty list check → `select_repository_url` → `self.normalize_repository_url(...)` → `Resolution`.
- New behavior: URL normalized; non-JSON response → warning (latent 500 fixed).

### Modified: `src/purl_resolver/resolver/librariesio.py`

- `class LibrariesIoResolver(HttpApiResolver)`; constructor `(api_key, timeout=15.0, retry_config=None)` → `super().__init__(timeout=..., max_requests_per_second=1.0, retry_config=...)` (hardcoded 1.0 preserved).
- Keeps: `ECOSYSTEM_MAP`, `_API_BASE`.
- `resolve()`: `_validate_purl` → platform map → `_get_json(purl, url, label="libraries.io", params={"api_key": self._api_key}, subject=f"{platform}/{name}")` → `repository_url` → `self.normalize_repository_url(...)` → `Resolution`.

### Modified: `src/purl_resolver/resolver/llm.py`

- `class LlmResolver(HttpResolver)`; constructor signature unchanged; `super().__init__(timeout=timeout)`; `AsyncOpenAI` client kept; `_http_client` removed.
- Attempts loop, `_validate_response`, `_RETRY_FEEDBACK`, prompt — unchanged. Per-attempt success path becomes:
  1. `_validate_response` → `repo_url` (purl echo, status, repository_url-string checks kept; the urlparse scheme check moves to normalization);
  2. `repo_url = self.normalize_repository_url(repo_url)` — `None` → `_record_failure(...)` → `continue`;
  3. `ok, head_error = await self._check_url(repo_url)` — SSRF-guarded HEAD via base → `url_check`; failure → `_record_failure` with reason → `continue`.
- Adds `async def close()` closing the `AsyncOpenAI` client.

### Modified: `src/purl_resolver/resolver/purl2repo.py`

- `Purl2RepoResolver` does **not** inherit `HttpResolver`/`HttpApiResolver` — it remains a direct `Resolver` subclass wrapping the purl2repo library via `asyncio.to_thread`.
- **Validation rules stay separate**: the library's own exception mapping is preserved (`UnsupportedEcosystemError` → warning, `Purl2RepoInvalidPurlError` → raise `InvalidPurlError`, `ResolutionError`/`MetadataFetchError` → raise `UpstreamError`, purl2repo.py:54-70).
- **Normalization is applied at our seam**: on a successful result, `normalize_repository_url(repo_url)` (module-level function from `base.py`) is called; `None` → warning `"Invalid repository URL from purl2repo for {purl}: {repo_url}"` and `Resolution` without a URL → chain falls through to depsdev. The library's internal file cache is untouched.

### Modified: `src/purl_resolver/routes/settings.py`

`_rebuild_resolvers` becomes async; before replacing the chain it closes old resolvers:

```python
for old in old_resolvers:
    close = getattr(old, "close", None)
    if close is not None:
        await close()
```

### Modified: `src/purl_resolver/main.py`

Lifespan `finally` block closes `app.state.resolvers` with the same duck-typing, before pool shutdown.

### Unchanged

`apk.py`, `factory.py` (signatures), `resolver/interface.py` (ABC), `retry.py`, service layer, storage, frontend, settings keys.

## Behavioral Changes

1. URL normalization applies chain-wide to all five resolvers (purl2repo, depsdev, ecosystems, librariesio, llm): https, no `.git`, no `/tree/`, `scm:`/`git://`/`ssh://`/`git@` converted. Non-normalizable URL → warning → chain continues (llm: attempt counted as failed).
2. LLM HEAD checks are SSRF-guarded; private-IP rejection reason is fed back into the prompt.
3. LLM normalizes before the HEAD check — the checked URL equals the stored URL.
4. Non-JSON responses from ecosyste.ms/libraries.io yield a warning instead of an unhandled `ValueError` (latent 500 fixed).
5. Warning formats preserved byte-identically; sole text change is the llm scheme-violation message.
6. httpx/OpenAI clients are closed on settings rebuild and shutdown (no more connection leaks).

## Testing

- **New `tests/test_url_check.py`**: `is_private_url` matrix (reserved networks, DNS failure, timeout); `head_url` (private before/after redirect → `ConnectionError`, status passthrough).
- **New `tests/test_resolver_base.py`**: `_check_url` outcomes and message formats; `normalize_repository_url` unit tests (first isolated coverage); `_get_json` error ladder; rate limiting (interval, zero → no sleep); `close()` calls `aclose`.
- **Modified `tests/test_llm_resolver.py`**: `make_llm_resolver` mocks `_check_url` instead of `_http_client`; new tests: normalization before HEAD (`http://` → `https://`), private-URL rejection with reason in warnings and prompt feedback.
- **Modified `tests/test_purl2repo_resolver.py`**: success-path normalization; unnormalizable URL → warning and chain fall-through.
- **Modified ecosystems/librariesio tests**: normalization of results; non-JSON response → warning.
- **Modified `tests/test_api.py`**: `_rebuild_resolvers` async; old resolvers closed on PATCH.
- Existing tests keep passing: `_client`/`_min_interval`/`_last_request_time` names preserved, rate-limit tests, depsdev `TestUrlNormalization`, warning-format assertions.

## Documentation

- `specs/architecture/layers.md`: Resolver Layer section gains `base.py` (`HttpResolver`/`HttpApiResolver`) and `url_check.py`; import rules updated (Resolver Layer → `url_check`; URL Validator → `url_check`); lifecycle `close()` documented.
- New ADR `specs/decisions/0009-http-resolver-base.md`: two-level hierarchy, common normalization policy, shared SSRF-guarded URL check, separated retry regimes, client lifecycle. `specs/INDEX.md` dependency graph updated.
- `CONTEXT.md`: unchanged — `HttpResolver`/`url_check` are implementation-level, not domain terms.
- This design doc lives in `docs/superpowers/specs/` per project convention.

## Out of Scope

Candidates B (ResolverChain module), C (batch module consolidation), D (storage seam split), E (frontend extraction) from the architecture review are not part of this change. `apk.py` is untouched; `purl2repo.py` changes only by the normalization call. LLM prompt, JSON schema validation, and settings keys are unchanged.
