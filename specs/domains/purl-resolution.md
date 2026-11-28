# PURL Resolution

## Description

Core capability of the system. Accepts one or more Package URL (PURL) strings and returns the corresponding source code repository URLs with warnings and resolver attribution. Uses a two-tier strategy: first checks PostgreSQL for a cached result, and on cache miss delegates resolution to the resolver chain (purl2repo → deps.dev → ecosyste.ms → libraries.io → apk → llm), storing successful results for future lookups. Resolver composition is settings-driven — each resolver after purl2repo can be toggled; the LLM resolver, when enabled, is always last and performs real web search via tool calls to a bundled SearXNG service. An optional source archive mode returns a download link for the exact version named in the PURL, using repository git tags and a deterministic version/tag matcher.

## Key Files

- `src/purl_resolver/router.py` — API endpoint handlers that call the Service Layer
- `src/purl_resolver/routes/resolve.py` — `POST /api/v1/resolve/batch` handler: batch repository resolution plus optional per-row source archive enrichment (`find_source_archive`, `force_refresh`); maps archive results to rows by index and derives `source_archive_commit_sha` from the commit archive URL
- `src/purl_resolver/source_archive/` — deterministic source archive lookup package: version/tag matching, git tag retrieval, GitHub archive URL construction and verification, and the `SourceArchiveService`
- `src/purl_resolver/source_archive/matching.py` — `TagInfo`/`TagMatch` types, `parse_version()`, `find_exact()`, and `find_near()`; numeric version extraction from tags, exact-match priority, and same-`major.minor` near matching
- `src/purl_resolver/source_archive/git_tags.py` — `fetch_tags()`: `git ls-remote --tags`, annotated-tag peeling, output/tag-count limits, timeout handling; `parse_ls_remote()`
- `src/purl_resolver/source_archive/github.py` — `parse_github_repository()`, `tag_archive_url()`, `commit_archive_url()`, `check_archive_url()`: GitHub-only repository parsing, archive URL construction, and redirected HEAD verification
- `src/purl_resolver/source_archive/service.py` — `SourceArchiveService`: cache lookup, validity check, repository/tag/URL resolution pipeline, batch deduplication and concurrency, per-row failure isolation, best-effort persistence of deterministic outcomes; `SourceArchiveResult`
- `src/purl_resolver/service.py` — `PurlResolutionService` class: Orchestration → validation → normalization → storage lookup → URL validation → resolver → storage store; `_resolve_concurrent()` core (semaphore + dedup by normalized key) shared by `resolve_many()` (batch endpoint, one row per input PURL) and `resolve_batch()` (SBOM flow, successful results only); `store_preexisting_references()` for SBOM pre-existing refs
- `src/purl_resolver/sbom_enrichment.py` — `SbomEnrichmentPipeline` orchestrating the full SBOM enrichment workflow: parse → collect → resolve → enrich → remove → report; used by async jobs (`routes/jobs.py`)
- `src/purl_resolver/purl_utils/` — PURL validation, normalization, and `safe_normalize()` convenience function
- `src/purl_resolver/resolver/` — Resolver abstraction (ABC, Resolution, exceptions), purl2repo wrapper, deps.dev wrapper, ecosyste.ms wrapper, libraries.io wrapper, apk wrapper, LLM wrapper, and factory module
- `src/purl_resolver/resolver/factory.py` — `build_resolvers(settings, app_settings, searxng_url="http://searxng:8080") → list[Resolver]`: centralizes resolver initialization; always creates Purl2RepoResolver, then conditionally adds DepsdevResolver, EcosystemsResolver, LibrariesIoResolver, ApkResolver, and LlmResolver (always last) based on settings; passes `searxng_url` and `llm_resolver_max_tool_rounds` to LlmResolver
- `src/purl_resolver/resolver/depsdev.py` — `DepsdevResolver`: fallback resolver using the deps.dev v3 API; enabled by default (settings-controlled), no API key required; supports: maven, npm, golang, pypi, nuget, cargo, gem; returns the package's SOURCE_REPO link normalized to an HTTPS URL
- `src/purl_resolver/resolver/ecosystems.py` — `EcosystemsResolver`: fallback resolver using ecosyste.ms Packages API, enabled by default (settings-controlled), no API key required (optional for higher rate limits)
- `src/purl_resolver/resolver/librariesio.py` — `LibrariesIoResolver`: fallback resolver using libraries.io API, optional (settings-controlled), supports: cargo, composer, conda, cpan, cran, gem, generic, golang, hackage, hex, maven, npm, nuget, pub, pypi, swift
- `src/purl_resolver/resolver/apk.py` — `ApkResolver`: fallback resolver for Alpine Linux APK packages (`pkg:apk/...`), returns constant URL `https://github.com/alpinelinux/aports`; purely local (no network calls), enabled by default via `apk_resolver_enabled` setting
- `src/purl_resolver/resolver/llm.py` — `LlmResolver`: last resolver in the chain; asks an OpenAI-compatible LLM for the repository URL using an unconditional tool-calling loop (`web_search` via SearXNG, `web_fetch` with SSRF guard), validates the JSON response schema and verifies the URL via HTTP HEAD (failed checks are fed back for the next attempt); optional (settings-controlled), always placed last
- `src/purl_resolver/config.py` — `SearxngSettings` (`SEARXNG_` prefix) exposes the internal SearXNG URL (`url`, default `http://searxng:8080`) as the `searxng_settings` singleton; read by `main.py` and `routes/settings.py` when building resolvers
- `src/purl_resolver/schemas.py` — Request and response data models
- `src/purl_resolver/storage/` — Storage Layer (interface, postgres, inmemory implementations)
- `src/purl_resolver/storage/source_archive.py` — `SourceArchiveRow` dataclass and the `SourceArchiveStorage` ABC (`lookup_archive`, `store_archive`), a storage surface separate from `Storage`
- `src/purl_resolver/storage/postgres_source_archive.py` — `PostgresSourceArchiveStorage`: `SELECT` by PURL and `INSERT ... ON CONFLICT (purl) DO UPDATE`
- `src/purl_resolver/storage/inmemory_source_archive.py` — `InMemorySourceArchiveStorage`: dictionary-backed fallback used when PostgreSQL is unavailable
- `src/purl_resolver/storage/schema.sql` — Table definitions for `jobs`, `resolved_purls`, and `purl_source_archives`
- `src/purl_resolver/sbom/parser.py` — CycloneDX SBOM validation and parsing
- `src/purl_resolver/sbom/collector.py` — Recursive component collection with path tracking, `needs_enrichment` and `has_subcomponents` detection
- `src/purl_resolver/sbom/enricher.py` — Inserts VCS external references into SBOM components
- `src/purl_resolver/sbom/remover.py` — Removes unresolved components without subcomponents from SBOM
- `src/purl_resolver/sbom/reporter.py` — Builds enrichment report with found/not_found/removed counts
- `src/purl_resolver/settings_store.py` — JSON-based application settings persistence (validate_db_urls, url_validation_timeout, revalidation_cooldown_hours, resolver toggles, API keys, LLM resolver settings including `llm_resolver_max_tool_rounds`, batch_semaphore_limit, batch_max_items, source_archive_timeout, source_archive_concurrency, job_ttl_hours, connectivity settings)
- `src/purl_resolver/url_validator.py` — URL validation via HTTP HEAD + multi-VCS probe (`_check_vcs`: git → svn → hg → fossil) with rate limit mitigation; returns `UrlValidationOutput` dataclass capturing the final URL after 3xx redirects
- `src/purl_resolver/url_validation_cache.py` — `UrlValidationCache`: diskcache-based URL validation result cache with TTL expiry; used by `UrlValidationService`
- `src/purl_resolver/validation_service.py` — `UrlValidationService`: wraps `validate_url()` with UrlValidationCache; consumed by `PurlResolutionService` and accessed by `SbomEnrichmentPipeline` through `PurlResolutionService.validation_service` property
- `src/purl_resolver/db_admin_service.py` — `DbAdminService`: encapsulates database admin operations (list, edit, import/export CSV) between API routes and Storage Layer
- `src/purl_resolver/job_manager.py` — `JobManager`: async background job processing for SBOM enrichment; manages job queue, worker tasks, cleanup
- `src/purl_resolver/job_repository.py` — `JobRepository`: PostgreSQL persistence for job records (`JobRecord` dataclass)
- `src/purl_resolver/routes/jobs.py` — Async SBOM enrichment job endpoints (`POST /api/v1/jobs/sbom-enrich`, `GET /api/v1/jobs`, etc.)
- `tests/test_api.py` — Integration tests for resolution workflow
- `tests/test_storage.py` — Unit tests for service and in-memory cache
- `tests/test_source_archive_*.py` — Unit tests for matching, `git ls-remote` parsing, GitHub URL construction/checking, archive storage, the service, and the batch API fields

## Core Types

```python
class BatchResolveRequest(BaseModel):
    purls: list[str]  # one PURL per list item
    find_source_archive: bool = False  # opt into source archive lookup
    force_refresh: bool = False        # bypass the archive cache (archive mode only)

class BatchResolveItem(BaseModel):  # one row per input PURL, in input order
    purl: str            # original input string (with version)
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""
    error: str | None = None  # invalid_purl / upstream_error for this row
    # Source archive fields: populated only in archive mode for rows without error
    source_archive_url: str | None = None
    source_archive_commit_url: str | None = None
    source_archive_commit_sha: str | None = None
    source_archive_match: str | None = None       # exact | near | repository_only | not_found | no_version
    source_archive_reason: str | None = None      # stable reason code
    source_archive_ref: str | None = None         # matched tag name
    source_archive_ref_type: str | None = None    # tag
    source_archive_matched_version: str | None = None
    source_archive_resolver: str = ""
    source_archive_cached: bool = False
    source_archive_resolved_at: str = ""

class BatchResolveResponse(BaseModel):
    results: list[BatchResolveItem]

class ResolveResponse(BaseModel):  # stored canonical form, purl is normalized
    purl: str  # normalized form: scheme:type/namespace/name
    repository_url: str | None = None
    warnings: list[str] = []
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""

class PurlComponents:
    scheme: str       # always "pkg"
    type: str
    namespace: str | None
    name: str
    version: str | None
    qualifiers: dict[str, str] | None
    subpath: str | None

class UrlValidationResult(Enum):
    VALID = "valid"
    INVALID = "invalid"
    NETWORK_ERROR = "network_error"
    RATE_LIMITED = "rate_limited"

@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None
    # final_url is str(resp.url) from httpx with follow_redirects=True
    # final_url is None only when HEAD request did not execute
    # (scheme error, rate-limit cooldown, connectivity failure, HEAD exception)

@dataclass(frozen=True)
class SourceArchiveRow:  # persisted row in purl_source_archives
    purl: str
    version: str
    match_type: str          # exact | near | repository_only | not_found
    reason: str | None = None
    archive_url: str | None = None
    archive_url_commit: str | None = None
    matched_ref: str | None = None
    matched_ref_type: str | None = None  # tag
    matched_version: str | None = None
    repository_url: str | None = None
    resolver: str = ""       # "git-tags"
    resolved_at: str = ""

@dataclass(frozen=True)
class SourceArchiveResult:  # service result, adds runtime-only fields
    purl: str
    match_type: str          # exact | near | repository_only | not_found | no_version
    reason: str | None = None
    archive_url: str | None = None
    archive_url_commit: str | None = None
    matched_ref: str | None = None
    matched_ref_type: str | None = None
    matched_version: str | None = None
    repository_url: str | None = None
    resolver: str = ""
    cached: bool = False
    resolved_at: str = ""
    warnings: list[str] = []

@dataclass(frozen=True)
class TagInfo:  # one tag from git ls-remote
    name: str
    commit_sha: str | None = None  # peeled commit SHA (annotated tags use ^{})

@dataclass(frozen=True)
class TagMatch:
    tag: TagInfo
    match_type: str    # exact | near
    matched_version: str
```

## Flow

```
Client                    API Layer (router)         Service Layer             purl_utils        Storage          Resolver
  |                          |                          |                        |                |                |
  | POST /api/v1/resolve/batch |                        |                        |                |                |
  | {"purls": ["pkg:...", ...]} |                       |                        |                |                |
  |------------------------->|                          |                        |                |                |
  |                          | service.resolve_many()   |                        |                |                |
  |                          |------------------------->|                        |                |                |
  |                          |   per unique PURL:      |                        |                |                |
  |                          |   service.resolve_purl() |                        |                |                |
  |                          |   validate(purl_str)     |                        |                |                |
  |                          |                          |----------------------->|                |                |
  |                          |                          | PurlComponents         |                |                |
  |                          |                          |<-----------------------|                |                |
  |                          |                          |                        |                |                |
  |                          |                          | (если ошибка)          |                |                |
  |                          |                          | HTTP 400               |                |                |
  |                          |                          |                        |                |                |
  |                          |                          | normalize(components)  |                |                |
  |                          |                          |----------------------->|                |                |
  |                          |                          | purl_key               |                |                |
  |                          |                          |<-----------------------|                |                |
  |                          |                          |                        |                |                |
  |                          |                          | storage.lookup(purl_key)|                |                |
  |                          |                          |--------------------------------------->|                |
  |                          |                          |                        |                |                |
  |                          |                          | (если найдено)         |                |                |
  |                          |                          | ResolveResponse        |                |                |
  |                          |                          |<---------------------------------------|                |
  |                          |                          |                        |                |                |
  |                          |                          | [если validate_db_urls |                |                |
  |                          |                          |  и resolved_at != сегодня]             |                |                |
   |                          |                          | validate_url(url, timeout)   |                |                |
    |                          |                          | ------+               |                |                |
    |                          |                          |        | HEAD + git   |                |                |
    |                          |                          | <------+               |                |                |
    |                          |                          |                        |                |                |
    |                          |                          | VALID → store(cached)  |                |                |
    |                          |                          |  (при отличии output.  |                |                |
    |                          |                          |   final_url URL в кеше |                |                |
    |                          |                          |   обновляется)         |                |                |
    |                          |                          | INVALID → delete, fall |                |                |
    |                          |                          | NETWORK_ERROR → return |                |                |
   |                          |                          |                        |                |                |
   |                          |                          | (если не найдено или  |                |                |
   |                          |                          |  cache deleted)        |                |                |
   |                          |                          | resolve(original_purl) |                |                |
   |                          |                          |------------------------------------------------------>|
   |                          |                          |                        |                |                |
   |                          |                          | ResolutionResult       |                |                |
   |                          |                          |<------------------------------------------------------|
   |                          |                          |                        |                |                |
   |                          |                          | (если success)         |                |                |
   |                          |                          | [если validate_db_urls  |                |                |
   |                          |                          |  включена]              |                |                |
    |                          |                          | validate_url(url, timeout)   |                |                |
    |                          |                          | ------+                |                |                |
    |                          |                          |        | HEAD + git    |                |                |
    |                          |                          | <------+                |                |                |
    |                          |                          |                        |                |                |
    |                          |                          | VALID → store + return |                |                |
   |                          |                          |  (используется output. |                |                |
   |                          |                          |   final_url для repo_url)               |                |                |
   |                          |                          | INVALID → continue to  |                |                |
   |                          |                          |           next resolver|                |                |
   |                          |                          | NETWORK_ERROR → store  |                |                |
   |                          |                          |           + return     |                |                |
   |                          |                          |                        |                |                |
   |                          |                          | [если validate_db_urls |                |                |
   |                          |                          |  выключена]            |                |                |
   |                          |                          | storage.store(result)  |                |                |
   |                          |                          |--------------------------------------->|                |
  |                          |                          |                        |                |                |
  |                          | 200 {results: [...]}     |                        |                |                |
  |<-------------------------|--------------------------|                        |                |                |
```

## LLM Web Search (tool-calling)

When the LLM resolver is enabled, every `resolve()` call passes the OpenAI Chat Completions `tools` parameter; the model decides what to search and when to fetch a page, and `LlmResolver` executes those calls on the host running sbom-helper.

### Tools

| Tool | Arguments | Result |
|---|---|---|
| `web_search` | `query` (string) | Up to 5 results formatted as title / URL / snippet, or `no results` |
| `web_fetch` | `url` (string) | Visible page text (up to 8000 characters), or a textual error |

`SYSTEM_PROMPT` instructs the model to call `web_search` when it does not know the repository, to call `web_fetch` when a candidate URL is ambiguous, and to return the same JSON object schema as before (`purl`, `status`, `repository_url`). The final JSON schema check and the HTTP HEAD check of the returned URL are unchanged.

### Tool-calling Loop

`_run_with_tools(messages)` makes at most `llm_resolver_max_tool_rounds + 1` model calls:

1. Call the model with `tools=TOOLS` and the accumulated `messages`.
2. If the assistant message has no `tool_calls`, return its content as the final answer.
3. Otherwise append the assistant message, execute every tool call in order, and append each result as a `role: "tool"` message with the matching `tool_call_id`.
4. Repeat until a final answer is produced or the round limit is reached.

Exhausting the round limit is a terminal outcome for that PURL: `resolve()` records an `exceeded max tool rounds` warning and does not run further `attempts_count` attempts. Tool errors (invalid arguments, unknown tool, search or fetch failure) are returned to the model as error strings and never raised.

### `web_search`

- Sends `GET {searxng_url}/search` with `params={"q": query, "format": "json"}` and a 15-second timeout.
- Rejects an empty query with an error string.
- Reads `results` from the JSON response and formats the first 5 entries as `title`, `url`, and `content` (snippet).
- Any HTTP, timeout, or JSON error becomes an error string returned to the model; it does not fail resolution.

### `web_fetch`

- Accepts only `http` and `https` URLs with a non-empty hostname; other schemes return an error string.
- Resolves the hostname with `socket.getaddrinfo` and rejects the request if **any** resolved address is non-global (including CGNAT/shared, private, loopback, link-local, reserved, multicast, unspecified). Hostname resolution failure or an empty resolution result is treated as forbidden.
- Follows redirects manually (`follow_redirects=False`) for at most 3 hops; the scheme and IP checks run again on every hop.
- Uses a dedicated `httpx.AsyncClient` with default TLS verification (`verify=True`), separate from the LLM client's `llm_resolver_verify_ssl` / `llm_resolver_ca_bundle` settings, which apply only to the LLM endpoint.
- Caps the response body at 512 KiB (reading stops at the cap), uses a 15-second request timeout, converts HTML to visible text with the standard library `html.parser`, normalizes whitespace, and returns at most 8000 characters.
- Every failure (unsupported scheme, forbidden host, too many redirects, HTTP error, timeout, decode error) becomes an error string returned to the model.

SearXNG is an internal compose service and is normally unavailable when the app runs outside Docker. In that case `web_search` returns an error to the model, and the resolver degrades to the model's own knowledge rather than failing.

## URL Validator

### URL Validator (`url_validator.py`)
- Validates repository URLs via HTTP HEAD + multi-VCS probe to verify the URL exists and is reachable
- `validate_url(url, timeout) → UrlValidationOutput` — performs HEAD (with `follow_redirects=True`), captures the final URL after all 3xx redirects via `str(resp.url)`, then runs `_check_vcs()` against the final URL; returns `UrlValidationOutput(result, final_url)`
- `ensure_connectivity(url=None, timeout=None) → bool` — connectivity probe against configurable URL (default `https://github.com`); raises `ConnectionError` on failure
- `_check_vcs(url, timeout) → bool | None` — unified multi-VCS probe; runs git → svn → hg → fossil sequentially with early-exit on first success; aggregation: `True` if any probe is `True`, else `False` if any is `False`, else `None`; called with the resolved final URL by `validate_url()`
- `_git_probe(url, timeout) → bool | None` — internal helper: `git ls-remote --exit-code <url>`
- `_svn_probe(url, timeout) → bool | None` — internal helper: `svn ls <url>`; exit 0 → True, exit ≠0 → False
- `_hg_probe(url, timeout) → bool | None` — internal helper: `hg identify <url>`; exit 0 → True, exit ≠0 → False
- `_fossil_probe(url, timeout) → bool | None` — combined probe: tries the authoritative /xfer protocol probe first (`_fossil_probe_xfer`), falls back to HTML footer regex (`_fossil_probe_footer`) when the xfer probe is uncertain (None)
- `_fossil_probe_xfer(url, timeout) → bool | None` — internal helper: minimal POST to `<url>/xfer` with `Content-Type: application/x-fossil-debug`; checks response Content-Type for `application/x-fossil` / `application/x-fossil-debug` → True; 401/403 → None (uncertain — auth required); other non-fossil response → False; transport error → None
- `_fossil_probe_footer(url, timeout) → bool | None` — internal helper (fallback): HTTP GET with `follow_redirects=True`; status 200 + footer regex match → True; status 200 without footer → False; non-200 → False; transport error → None
- `UrlValidationResult` enum — `VALID`, `INVALID`, `NETWORK_ERROR`, `RATE_LIMITED`
- `UrlValidationOutput` dataclass — `result: UrlValidationResult`, `final_url: str | None = None`; `final_url` is `str(resp.url)` after redirects, `None` when HEAD did not execute (scheme error, cooldown, connectivity failure, HEAD exception)

## UrlValidationService

### Service Wrapper (`validation_service.py`)
- `UrlValidationService` wraps `validate_url()` with UrlValidationCache
- `UrlValidationService.__init__(settings_store: SettingsStore, cache: UrlValidationCache)` — receives `SettingsStore` for cooldown/retry config and `UrlValidationCache` for caching validation results
- `UrlValidationService.validate_url(url, timeout) → UrlValidationOutput` — checks cache first (within cooldown window), then delegates to `validate_url()`; caches VALID results
- `UrlValidationService.clear_cache() → None` — clears the entire validation cache
- Consumed by `PurlResolutionService` as an optional dependency. `SbomEnrichmentPipeline` accesses `validation_service` through `PurlResolutionService.validation_service` property.
- Decouples URL validation setup from resolution orchestration; single point for validation configuration changes

## Source Archive Resolution

Optional mode of `POST /api/v1/resolve/batch` that returns a GitHub archive URL for the version named in the PURL. Repository resolution keeps its existing versionless cache and resolver chain; archive data is stored separately per versioned PURL.

### Cache Key and Storage

- Cache key: `normalize_with_version(validate(purl))` — canonical PURL including `version`, with qualifiers and subpath removed (for example `pkg:github/ClickHouse/ClickHouse@23.8.16.40`).
- `SourceArchiveStorage` (`storage/source_archive.py`) is an ABC separate from `Storage`: `lookup_archive(purl) → SourceArchiveRow | None` and `store_archive(row) → None`.
- `PostgresSourceArchiveStorage` reads with `SELECT * FROM purl_source_archives WHERE purl = $1` and writes with `INSERT ... ON CONFLICT (purl) DO UPDATE` for every data column. A read normalizes `resolved_at` to an ISO-8601 string, matching freshly computed results.
- `InMemorySourceArchiveStorage` keeps a dictionary keyed by PURL and is used when PostgreSQL is unavailable, matching the `resolved_purls` degradation path.
- `main.py` creates the storage next to `PostgresCache` and injects it into `SourceArchiveService`; both storages switch together.

### Version and Tag Matching

Tag names and the PURL version are normalized by extracting the longest chain of digit groups separated only by `.`, `-`, `_`, `/`, or `+`:

- Text before the chain is a prefix (`v`, `release`, project name) and is ignored.
- Text after the chain is a suffix normalized to lowercase alphanumerics (`lts`, `rc1`, `stable`).
- `v23.8.16.40-lts` → `(23, 8, 16, 40)` + `lts`; `rel_23_8_16_40` → `(23, 8, 16, 40)`; `release-1.2.3` → `(1, 2, 3)`; `v1.2.3-rc4` → `(1, 2, 3)` + `rc4`.
- Tags without digits never match. A PURL version without digits yields `non_numeric_version`.
- Numeric tuples are compared component-wise with missing components padded by zeros, so `1.2` and `1.2.0` are equal.

**Exact (`exact`)** — equal numeric tuples; if the PURL version has a non-numeric suffix, the tag suffix must equal it (case-insensitive); if the PURL version has no suffix, any tag suffix is accepted. Several exact tags are ordered by: no pre-release marker (`rc`, `alpha`, `beta`, `pre`, `dev`, `snapshot`, `nightly`) first, then shorter tag name, then lexicographically smaller tag name. More than one exact candidate adds the warning `Multiple exact tags matched; chose '<tag>'`.

**Near (`near`)** — only tags with the same `major.minor` are considered; pre-release tags are excluded unless the PURL version itself is a pre-release; an equal numeric tuple with a different suffix counts as near. Priority: equal numeric tuple first, then the highest version below the target, then the lowest version above the target. `matched_version` carries the numeric version of the selected tag.

The first version uses deterministic matching only; no LLM is consulted for tag selection.

### Tag Retrieval

`git_tags.fetch_tags(repository_url, timeout)` runs `git ls-remote --tags <repository_url>` via `asyncio.create_subprocess_exec` with `GIT_TERMINAL_PROMPT=0` and `GIT_ASKPASS=/bin/true`.

- Only `http(s)` URLs with a non-empty hostname are accepted; other inputs raise `GitTagsError` (reported as `git_error` by the service).
- The process is killed on timeout (`source_archive_timeout`) and tracked through the shared subprocess helpers in `url_validator.py`.
- Output is capped at 5 MB and 50 000 tags; exceeding either raises `GitTagsError`.
- Lines `refs/tags/<tag>` and `refs/tags/<tag>^{}` are parsed; the peeled `^{}` commit SHA replaces the annotated tag-object SHA, so `TagInfo.commit_sha` always refers to a commit when available.

### GitHub Archive URLs

`github.parse_github_repository()` accepts only `github.com` and `www.github.com` with a path of exactly `/{owner}/{repo}`; a trailing `/` and `.git` suffix are stripped, and owner/repo must match `^[A-Za-z0-9_.-]+$` and must not be `.` or `..`. A repository URL that `urlsplit` cannot parse yields `None`.

- Tag URL: `https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.tar.gz`; the tag is percent-encoded with `/` preserved.
- Commit URL: `https://github.com/{owner}/{repo}/archive/{sha}.tar.gz`; the SHA must be 40 hex characters.
- `check_archive_url(url, timeout)` performs HTTP HEAD with `follow_redirects=True` and returns `True` only for a final status below 400. GitHub redirects archives to `codeload.github.com`, so redirects are required.

### Lookup Order

For one PURL the service executes:

1. `validate(purl)`; a valid PURL without `version` returns `no_version` / `no_version` (not persisted, no git call).
2. Extract the numeric version; no digits returns `non_numeric_version` with `repository_only` when a repository URL exists and `not_found` otherwise (not persisted).
3. Build the versioned cache key.
4. Unless `force_refresh` is set, read the cache. A hit is returned with `cached=True` unless the current non-null repository URL differs from the stored `repository_url`; a differing repository marks the row stale and the lookup continues. A cached row whose reason is transient (`git_error`, `archive_check_failed`, `internal_error`) is treated as a miss. When the current repository URL is `None`, the stored row is still returned.
5. No repository URL → `not_found` / `no_repository`; store.
6. Non-GitHub repository → `repository_only` / `unsupported_host`; store.
7. Tag fetch failure → `repository_only` / `git_error`; return without storing.
8. Exact tag → HEAD check; success stores `exact`, failure returns `repository_only` / `archive_check_failed` without storing.
9. Near tag → HEAD check; success stores `near`, failure returns `repository_only` / `archive_check_failed` without storing.
10. No match → `repository_only` / `no_matching_tag`; store.
11. An unexpected exception while resolving one row is isolated: the row returns `repository_only` / `internal_error` when a repository URL exists, `not_found` / `internal_error` otherwise, and the row is not stored. Other rows in the batch are unaffected.
12. A storage failure is logged and the computed result is still returned.

`SourceArchiveService.enrich_many()` deduplicates identical `(cache key, repository_url)` pairs, preserves input order, and bounds lookups with a semaphore set from `source_archive_concurrency`; this semaphore is separate from `batch_semaphore_limit`.

### Match Types and Reasons

| `match_type` | Persisted | `archive_url` | Meaning |
|---|---|---|---|
| `exact` | yes | set | Tag version equals the PURL version after normalization |
| `near` | yes | set | Nearest tag in the same `major.minor`; `matched_version` differs |
| `repository_only` | deterministic outcomes only | `NULL` | No archive link; a repository may be known |
| `not_found` | deterministic outcomes only | `NULL` | Neither archive link nor repository |
| `no_version` | no (API only) | `NULL` | The PURL has no version |

`repository_only` rows with `unsupported_host` or `no_matching_tag` and `not_found` rows with `no_repository` are deterministic and persisted. `repository_only` / `not_found` rows with a transient reason (`git_error`, `archive_check_failed`, `internal_error`) are returned but not stored. Rows produced by `non_numeric_version` use `repository_only` or `not_found` in the response but are not persisted.

`reason` is mutually exclusive and follows this precedence; `exact` and `near` rows carry `NULL`:

| Order | `reason` | Condition |
|---|---|---|
| 1 | `no_version` | PURL has no version |
| 2 | `non_numeric_version` | PURL version has no digit chain |
| 3 | `no_repository` | Repository URL is absent |
| 4 | `unsupported_host` | Repository is not GitHub |
| 5 | `git_error` | `git ls-remote` failed (network, private repository, timeout, limits) |
| 6 | `archive_check_failed` | Constructed archive URL failed the HEAD check |
| 7 | `no_matching_tag` | Tags were fetched but neither exact nor near matched |
| 8 | `internal_error` | Unexpected per-row failure during archive lookup |

`no_version` and `non_numeric_version` are returned in the API row and never stored as archive cache rows. `git_error`, `archive_check_failed`, and `internal_error` are returned but not stored.

Only deterministic outcomes are cached, including negative ones: `exact`, `near`, `repository_only` with `unsupported_host` or `no_matching_tag`, and `not_found` with `no_repository`. Transient outcomes (`git_error`, `archive_check_failed`, `internal_error`) are recomputed on the next request. `force_refresh=true` bypasses only the archive cache; the versionless `resolved_purls` cache is still used for the repository URL. Archive rows persist until a `force_refresh` lookup overwrites them or a `--mode replace` restore truncates them; a default `merge` restore keeps existing archive rows. There is no TTL or background refresh.

### Backup and Restore

`scripts/db_backup.sh` writes a two-file set:

- `backups/sbom_purls_YYYYmmdd-HHMMSS.csv.gz` — `resolved_purls` (`purl`, `repository_url`, `resolver`, `resolved_at`), unchanged;
- `backups/sbom_source_archives_YYYYmmdd-HHMMSS.csv.gz` — `purl_source_archives` with the exact column order `purl,version,match_type,reason,archive_url,archive_url_commit,matched_ref,matched_ref_type,matched_version,repository_url,resolver,resolved_at`, sorted by `purl`, exported with `PGTZ=UTC`.

`-o FILE`/`--output FILE` sets the PURL mapping path; the archive file is written beside it: `out.csv.gz` becomes `out.source_archives.csv.gz`, and a name without the `.csv.gz` suffix gets `.source_archives.csv.gz` appended. Without `-o`, both files share one UTC timestamp. `--keep N` groups files by their `YYYYmmdd-HHMMSS` suffix and removes whole old sets, keeping the `N` newest stamps; a file whose counterpart is missing still belongs to its stamp group and is removed with it, while files without a timestamp are not rotated.

`scripts/db_restore.sh` accepts one or both files in any order and detects the target table from the exact CSV header, so old PURL-only backups keep working; two files for the same table are rejected.

- `--mode merge` (default) inserts only missing `purl` values and keeps existing rows on the target stand for both tables.
- `--mode replace` truncates the table and inserts from a staging table in one transaction, applied independently per supplied table; an empty file for replace is rejected.
- `inserted`, `skipped`, and `total` counters are printed per table; staging tables are created with `LIKE <table> INCLUDING DEFAULTS` and dropped on exit.

## Invariants

- `POST /api/v1/resolve/batch` always returns HTTP 200 with one result row per input PURL, in input order
- Every valid PURL row: `repository_url: null` if unresolved, `error: null`
- Invalid PURL format is caught at the application level (purl_utils) before any resolver or storage call — the row carries `error: "invalid_purl"` instead of failing the whole request
- Unsupported ecosystems return a row with `repository_url: null` and a warning (purl2repo returns `Resolution(None)`, resolver chain continues)
- Upstream errors (registry timeout, network failure) produce a row with `error: "upstream_error"`
- More than `batch_max_items` PURLs in one request → HTTP 400 `batch_too_large`
- Network connectivity probe failure → HTTP 503 `network_unavailable`
- The response format is canonical — it does not expose purl2repo's internal structure
- Empty purl strings are rejected at the Pydantic validation level (HTTP 422)
- **Normalized cache keys**: storage uses `scheme:type/namespace/name` form — version/qualifiers/subpath are stripped
- **Resolver receives original PURL**: the full string (with version, qualifiers, subpath) is passed unmodified to resolvers
- **DB cache hit**: if a result is found in PostgreSQL, the resolver is NOT called; when `validate_db_urls` is enabled, the cached URL is re-validated unless it is still within the validation cooldown window (`revalidation_cooldown_hours`)
- **Only successful results are stored**: `repository_url = null` results are never persisted
- **Graceful degradation**: if PostgreSQL is unavailable, the resolver still works (without caching)
- **Store is best-effort**: a failure to store does not break the response to the client
- **URL validation is optional**: controlled by `validate_db_urls` setting (default: off). When enabled, validation applies to both cached entries and freshly resolved URLs. For cached entries, cooldown (`revalidation_cooldown_hours`) skips re-validation; for fresh entries, validation runs synchronously before storing/returning.
- **Fresh URL validation skips invalid results**: when `validate_db_urls=true`, a freshly resolved URL returning `INVALID` via `validate_url()` causes the resolver chain to continue to the next resolver. The invalid result is neither stored nor returned. `NETWORK_ERROR` and `RATE_LIMITED` results keep the current resolver's result (store + return) to avoid discarding potentially valid URLs due to transient errors.
- **Validation cooldown applies uniformly**: the `revalidation_cooldown_hours` window is enforced per URL via the URL validation cache (diskcache) for all cached entries, regardless of the resolver that produced them
- **Cooldown disabled at zero**: Setting `revalidation_cooldown_hours=0` disables cooldown entirely — every cached entry triggers validation when `validate_db_urls=true`
- **SBOM existing-ref validation**: Optional checkbox `validate_existing_refs` in SBOM Updater validates existing VCS references via HEAD + multi-VCS probe (`_check_vcs`); `INVALID` results mark the component for re-resolution (`needs_enrichment=True`)
- **SBOM validation progress**: during the `validating_refs` phase the pipeline reports progress over unique VCS URLs (`(0, total)` followed by one update per validated URL), so the job progress bar reflects the validation stage the same way it does for PURL resolution
- **Connection errors preserve cache**: network errors during validation return `NETWORK_ERROR`, preserving the cached URL
- **Validation never crashes**: `validate_url()` always returns a `UrlValidationOutput`, never raises exceptions
- **Non-HTTP/HTTPS URLs skip redirect resolution**: URLs are validated by syntax (non-empty hostname) and SSRF guard (non-private IP) before VCS probes. HTTP/HTTPS URLs additionally undergo HEAD redirect resolution. Non-HTTP/HTTPS URLs skip redirect resolution and go directly to VCS probes.
- **revalidation_cooldown_hours bounds**: validated server-side with `ge=0, le=720` in both `AppSettings` and `SettingsUpdate`
- **Resolver field tracks origin**: every stored record has a `resolver` field indicating how it was added — `"purl2repo"`, `"depsdev"`, `"ecosyste.ms"`, `"libraries.io"`, `"apk"`, or `"llm"` when the corresponding resolver found the result, `"import-sbom"` for SBOM enrichment, `"import-csv"` for CSV import, `"import-manual"` for manual DB admin creation
- **Four-column table**: `resolved_purls` stores only `purl`, `repository_url`, `resolver`, `resolved_at` — all other fields from earlier schema versions have been removed
- **Warnings are runtime-only**: `warnings` is retained in `Resolution` dataclass, `ResolveResponse` model, and API response but is never persisted to the database, CSV export, or in-memory storage
- **Index on resolver**: `idx_resolved_purls_resolver` is created on startup in `create_pool()` to accelerate `SELECT DISTINCT resolver` queries for the dynamic resolver filter
- **URL redirects are resolved on validation**: `validate_url()` returns `UrlValidationOutput` containing the final URL after all 3xx redirects; `final_url` is `str(resp.url)` from httpx with `follow_redirects=True`
- **VCS probe uses the resolved final URL**: `_check_vcs()` receives the final redirect target, not the original URL
- **Cache entries updated with final URL on VALID**: `_validate_cached_url()` updates `cached.repository_url` when `final_url` differs from the stored URL on `VALID` result only
- **Fresh resolver results use final URL**: `resolve_purl()` stores and returns the resolved final URL for any non-INVALID validation result (including `NETWORK_ERROR`/`RATE_LIMITED`)
- **SBOM refs updated on any non-INVALID result**: `sbom_enrichment.py` updates `ref["url"]` with `final_url` when the ref redirected, regardless of whether validation result was `VALID`, `NETWORK_ERROR`, or `RATE_LIMITED`
- **SBOM enrichment uses resolver="import-sbom"**: both `PurlResolutionService.resolve_batch()` and `PurlResolutionService.store_preexisting_references()` in the SBOM flow store records with `resolver: "import-sbom"`
- **SBOM deduplication validates each PURL explicitly**: the deduplication loop calls `validate()` then `normalize()` on every component PURL; unversioned valid PURLs (e.g. `pkg:pypi/ptaf-task-manager`) are correctly normalized and added to the resolution queue — only truly invalid PURLs are counted as skipped
- **CSV import uses resolver="import-csv"**: when the `resolver` column is absent from the imported CSV, the value `"import-csv"` is used as default
- **SBOM enrichment enriches before removing**: `enrich_sbom()` is called before `remove_unresolved_components()` to avoid stale component paths after in-place removal
- **Removed components excluded from not_found**: components with `status: "removed"` do not appear as `status: "not_found"` in the report
- **Multi-VCS validation**: `_check_vcs()` probes git (via `git ls-remote --exit-code`), svn (via `svn ls`), hg (via `hg identify`), fossil (via HTTP GET + footer regex) sequentially with early-exit on first success
- **VCS aggregation rule**: if any probe returns `True` → result `True`; else if any probe returns `False` → result `False`; else (all probes uncertain) → result `None`
- **Docker provides VCS tools**: `git`, `subversion`, `mercurial` are installed in both `dev` and `prod` stages of the Dockerfile; fossil uses HTTP (httpx) and requires no binary
- **VCS subprocess timeouts are non-fatal**: `asyncio.TimeoutError` from any subprocess call is treated as `None` (uncertain) and logged as a warning; never raised to the caller
- **UrlValidationService is optional**: `PurlResolutionService` accepts an optional `validation_service: UrlValidationService | None` parameter; when `None`, callers fall back to direct `validate_url()` calls. `SbomEnrichmentPipeline` accesses `validation_service` through `PurlResolutionService.validation_service` property
- **Source archive lookup is opt-in**: `find_source_archive=false` (the default) performs no archive work and leaves every `source_archive_*` field at its null/empty default; `force_refresh` has no effect unless `find_source_archive=true`
- **Archive rows align with resolution rows**: archive results are mapped back to the successful (error-free) result rows by index, so rows with a per-row error keep null/empty archive fields and a failure in archive lookup never changes the HTTP status of another row
- **Archive cache key includes the version**: `purl_source_archives.purl` is the canonical PURL with `version` and without qualifiers or subpath; one row exists per versioned PURL and `store_archive` overwrites it
- **Archive cache stores deterministic outcomes only**: `exact`, `near`, `repository_only` with `unsupported_host`/`no_matching_tag`, and `not_found` with `no_repository` are cached; the transient `git_error`, `archive_check_failed`, and `internal_error` outcomes are returned per request and never written to `purl_source_archives`
- **API-only outcomes are not persisted**: `no_version` (match type and reason) and `non_numeric_version` (reason) are computed and returned per request but never written to `purl_source_archives`; their `source_archive_resolver` and `source_archive_resolved_at` fields are empty strings
- **Archive reason precedence is fixed**: the first applicable code in the order `no_version`, `non_numeric_version`, `no_repository`, `unsupported_host`, `git_error`, `archive_check_failed`, `no_matching_tag`, `internal_error` is the reported reason; `exact` and `near` rows report `reason = NULL`
- **Archive lookup failures are isolated per row**: an unexpected exception while resolving one row produces `repository_only` / `internal_error` when a repository URL exists and `not_found` / `internal_error` otherwise; the row is not stored and other rows, including the HTTP status, are unaffected. A batch-wide failure inside `enrich_many` likewise falls back to per-row `internal_error` results instead of a 5xx
- **Repository change invalidates a cached archive**: a cache hit is returned only when the current repository URL is `None` or equals the stored `repository_url`; a current non-null repository URL that differs forces a fresh lookup and overwrites the row
- **force_refresh bypasses only the archive cache**: `force_refresh=true` ignores `purl_source_archives` for the request and recomputes those rows; repository resolution still uses the versionless `resolved_purls` cache
- **Archive matching is deterministic**: tag selection uses numeric-tuple comparison, suffix rules, pre-release ordering, and same-`major.minor` bounds; no LLM participates in matching
- **Archive URLs are verified before storage**: only HEAD-checked tag URLs become `exact`/`near` results; the check follows redirects and accepts final statuses below 400
- **Commit URLs are derived from a 40-hex SHA**: `archive_url_commit` is populated whenever `git ls-remote` yields a 40-hex SHA for the matched tag; `source_archive_commit_sha` is the 40-hex path segment of that commit URL. A non-40-hex SHA omits the commit URL and does not fail the row
- **Archive lookup is GitHub-only**: non-GitHub repositories produce `repository_only` / `unsupported_host` and never trigger archive URL construction
- **Tag retrieval uses git only**: `git ls-remote --tags` supplies tag names and SHAs; the GitHub REST API and GitHub tokens are not used for source archives
- **Archive warnings are runtime-only**: archive warnings (such as the multiple-exact-tags notice) are returned with the computed result and are not persisted, so a cache hit returns an empty `warnings` list for the archive portion
- **Archive storage is best-effort**: any lookup or store failure in `SourceArchiveStorage` is logged and the computed archive result is still returned
- **Archive concurrency is independent**: `source_archive_concurrency` bounds archive lookups per batch and does not replace `batch_semaphore_limit`
- **Archive lookups are deduplicated per batch**: inputs that share the versioned cache key and repository URL are resolved once and the result is reused for every matching row
- **LLM tool-calling is unconditional**: when the LLM resolver is enabled, every chat completion request includes the `web_search` and `web_fetch` tool definitions, regardless of model or settings
- **LLM tool rounds are bounded and terminal**: a single attempt makes at most `llm_resolver_max_tool_rounds + 1` model calls; exhausting the limit ends resolution for that PURL without further `attempts_count` attempts
- **LLM tool failures degrade, never raise**: search and fetch errors, invalid tool arguments, and unknown tool names are returned to the model as text; they do not abort resolution or change the API response shape
- **`web_fetch` enforces an SSRF boundary**: only `http`/`https`; every hostname is resolved on each hop and non-global (including CGNAT/shared, private, loopback, link-local, reserved, multicast, unspecified) addresses are rejected; redirects are followed manually for at most 3 hops, and the scheme/IP checks repeat on every hop
- **`web_fetch` limits apply independently of LLM TLS settings**: it uses its own HTTP client with default TLS verification, a 15-second timeout, a 512 KiB body cap, and at most 8000 characters of extracted text; `llm_resolver_verify_ssl` and `llm_resolver_ca_bundle` affect only the LLM endpoint
- **SearXNG is an internal dependency**: the app calls `SEARXNG_URL` (default `http://searxng:8080`), a compose service with no published port; if SearXNG is unreachable, `web_search` returns an error to the model and resolution continues instead of failing
- **LLM resolution still requires a valid final answer**: after tool use, the response must be the expected JSON object with a matching PURL and an `http(s)` `repository_url`, and the URL must pass the HTTP HEAD check

## Configuration

### Environment Variables

| Key | Default | Description |
|---|---|---|
| `PURL2REPO_TIMEOUT` | `15.0` | Timeout for purl2repo HTTP requests (seconds) |
| `PURL2REPO_USE_CACHE` | `true` | Enable purl2repo file-based caching |
| `PURL2REPO_STRICT` | `false` | Strict mode — purl2repo raises instead of returning warnings |
| `PURL2REPO_NO_NETWORK` | `false` | Disable network access for purl2repo |
| `PURL2REPO_CACHE_DIR` | `None` | Custom cache directory path for purl2repo |
| `DB_URL` | `postgresql://sbom:sbom@localhost:5432/sbom` | PostgreSQL connection string |
| `DB_POOL_MIN_SIZE` | `2` | Minimum asyncpg pool connections |
| `DB_POOL_MAX_SIZE` | `10` | Maximum asyncpg pool connections |
| `SBOM_MAX_FILE_SIZE` | `209715200` (200 MB) | Maximum uploaded SBOM file size (bytes) |
| `SETTINGS_FILE` | `./data/settings.json` | Path to JSON settings file |
| `SEARXNG_URL` | `http://searxng:8080` | Internal SearXNG base URL used by the LLM resolver's `web_search` tool (`SEARXNG_` prefix, `SearxngSettings`) |

### JSON Settings (`data/settings.json`)

| Key | Default | Description |
|---|---|---|
| `validate_db_urls` | `false` | Enable URL validation for cached repository URLs |
| `validate_sbom_refs` | `false` | Enable URL validation for existing VCS references in SBOM files |
| `sbom_multiple_vcs_behavior` | `"keep-first"` | Behavior when SBOM component has multiple VCS refs (`"keep-first"` or `"keep-all"`) |
| `url_validation_timeout` | `5` | Timeout in seconds for HEAD and multi-VCS probe checks (1–60) |
| `librariesio_enabled` | `false` | Enable libraries.io as a fallback resolver after purl2repo |
| `librariesio_api_key` | `null` | Libraries.io API key for higher rate limits (60 req/min vs 10 req/min) |
| `depsdev_enabled` | `true` | Enable deps.dev as a fallback resolver after purl2repo (no API key required) |
| `revalidation_cooldown_hours` | `24` | Re-validation cooldown in hours (0 = no cooldown, max 720) |
| `ecosystems_enabled` | `true` | Enable ecosyste.ms as a fallback resolver |
| `apk_resolver_enabled` | `true` | Enable APK resolver (Alpine Linux) fallback — returns `https://github.com/alpinelinux/aports` for any `pkg:apk/...` PURL |
| `ecosystems_api_key` | `null` | Optional API key for ecosyste.ms (higher rate limits) |
| `ecosystems_max_requests_per_second` | `2.0` | Rate limit for ecosyste.ms API requests (0.1–100) |
| `retry_max_attempts` | `3` | Maximum HTTP request attempts per resolver (1–10). Applied to ecosyste.ms and libraries.io on timeout, 429, and 5xx errors. |
| `retry_base_cooldown_seconds` | `5.0` | Base wait time between retries; actual wait = cooldown × (attempt − 1). Range: 0.5–120. |
| `batch_semaphore_limit` | `10` | Maximum concurrent resolution requests in batch mode (1–100) |
| `batch_max_items` | `100` | Maximum PURLs per batch request (1–1000) |
| `source_archive_timeout` | `30.0` | Timeout in seconds for `git ls-remote` and the archive HEAD check (1–300) |
| `source_archive_concurrency` | `5` | Maximum concurrent source archive lookups per batch request (1–50) |
| `job_ttl_hours` | `24` | Time-to-live in hours for async job records (1–720) |
| `connectivity_url` | `"https://github.com"` | URL used for connectivity probes |
| `connectivity_timeout` | `2` | Timeout in seconds for connectivity probes (1–30) |
| `log_level` | `"INFO"` | Application log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `language` | `"en"` | UI language (`"en"` or `"ru"`) |
| `json_indent` | `4` | Number of spaces for JSON indentation in downloaded files (1, 2, or 4) |
| `llm_resolver_enabled` | `false` | Enable the LLM resolver as the last resolver in the chain |
| `llm_resolver_base_url` | `null` | OpenAI-compatible API base URL (`^https?://`) |
| `llm_resolver_api_key` | `null` | LLM API key |
| `llm_resolver_model` | `null` | LLM model name |
| `llm_resolver_attempts_count` | `2` | Total LLM attempts per PURL (1–10) |
| `llm_resolver_timeout` | `60` | LLM request timeout in seconds (1–600) |
| `llm_resolver_max_tool_rounds` | `3` | Maximum tool-calling rounds per LLM attempt (1–10); exhausting it ends resolution for the PURL |

## Database Schema

The `resolved_purls` table stores resolution results:

| Column | Type | Constraints |
|---|---|---|
| `purl` | `TEXT` | `PRIMARY KEY` |
| `repository_url` | `TEXT` | `NOT NULL` |
| `resolver` | `TEXT` | `NOT NULL` |
| `resolved_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` |

Created on startup via `CREATE TABLE IF NOT EXISTS`. Schema is defined in `storage/schema.sql` alongside the `jobs` table. An index on `resolver` column (`idx_resolved_purls_resolver`) is created after the table to accelerate `SELECT DISTINCT resolver` queries.

The `purl_source_archives` table caches source archive lookups by versioned PURL:

| Column | Type | Constraints |
|---|---|---|
| `purl` | `TEXT` | `PRIMARY KEY` — canonical PURL with version, without qualifiers/subpath |
| `version` | `TEXT` | `NOT NULL` — PURL version as supplied |
| `match_type` | `TEXT` | `NOT NULL` — `exact`, `near`, `repository_only`, or `not_found` |
| `reason` | `TEXT` | nullable — stable reason code for `repository_only`/`not_found` |
| `archive_url` | `TEXT` | nullable — main tag archive URL for `exact`/`near` |
| `archive_url_commit` | `TEXT` | nullable — commit archive URL when a SHA is known |
| `matched_ref` | `TEXT` | nullable — matched tag name |
| `matched_ref_type` | `TEXT` | nullable — `tag` |
| `matched_version` | `TEXT` | nullable — numeric version of the matched tag |
| `repository_url` | `TEXT` | nullable — repository used to build the link |
| `resolver` | `TEXT` | `NOT NULL` — `git-tags` |
| `resolved_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` |

`idx_purl_source_archives_match_type` indexes `match_type` for filtering and diagnostics. The table is created on startup together with `resolved_purls`.
