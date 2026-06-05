# Libraries.io Resolver — Design

## Problem

purl2repo does not find repositories for some ecosystems. An additional data source is needed to improve coverage.

## Solution

Add a `LibrariesIoResolver` as a fallback resolver in the existing resolver chain. The resolver queries the libraries.io API to find repository URLs for packages that purl2repo cannot resolve.

## Decisions

1. **Fallback behavior**: purl2repo is tried first; libraries.io is used only if purl2repo does not find a repository URL.
2. **Used in enrichment**: libraries.io resolver participates in both single PURL resolution and SBOM file enrichment.
3. **Optional**: Disabled by default. Enabled via checkbox + API key in the Settings page.
4. **Graceful degradation**: Errors from libraries.io (timeouts, 429, 5xx, network failures) are logged as warnings and do not interrupt processing. The resolver returns `Resolution()` with no URL, allowing the chain to continue.
5. **Custom rate limiter**: Minimum 1 second between requests, enforced via `time.monotonic()` + `time.sleep()`. libraries.io allows 60 req/min with an API key.
6. **Key validation at save time**: The API key is validated via `GET https://libraries.io/api/platforms?api_key={key}` before saving. Network errors during validation do not block saving.

## Architecture

### New file: `src/purl_resolver/resolver/librariesio.py`

```python
class LibrariesIoResolver(Resolver):
    ECOSYSTEM_MAP = {
        'cargo': 'Cargo',
        'composer': 'Packagist',
        'conda': 'Conda',
        'cpan': 'CPAN',
        'cran': 'CRAN',
        'gem': 'RubyGems',
        'generic': 'GitHub',
        'golang': 'Go',
        'hackage': 'Hackage',
        'hex': 'Hex',
        'maven': 'Maven',
        'npm': 'NPM',
        'nuget': 'NuGet',
        'pub': 'Pub',
        'pypi': 'PyPI',
        'swift': 'SwiftPM',
    }

    @property
    def name(self) -> str:
        return "libraries.io"

    def __init__(self, api_key: str, timeout: float = 15.0):
        self._api_key = api_key
        self._timeout = timeout
        self._min_interval = 1.0  # seconds between requests
        self._last_request_time = 0.0
        self._client = httpx.Client(timeout=timeout)

    def resolve(self, purl: str) -> Resolution:
        # 1. Parse PURL → extract type, name, namespace
        # 2. Map PURL type to libraries.io platform
        #    If unknown → return Resolution() with warning
        # 3. Rate limit: time.sleep() if needed
        # 4. GET https://libraries.io/api/{platform}/{name}?api_key={key}
        # 5. Parse response → extract repository_url
        # 6. Return Resolution with repository_url, type, kind, confidence, evidence
        # 7. On any error → log warning, return Resolution() with warning
```

**Key behaviors:**
- Unknown PURL type → returns `Resolution()` with warning, no exception
- API error (timeout, 429, 5xx, 401, 403) → logs warning, returns `Resolution()` with warning
- Rate limiter ensures minimum 1-second gap between requests using `time.sleep()`
- `repository_url` extracted from `repository.url` field in libraries.io response
- `repository_kind` set to `"source"` (libraries.io provides source repository URLs)
- `confidence` set to `"medium"` (libraries.io data is curated but not always authoritative)
- `evidence` includes `["libraries.io:{platform}/{name}"]`
- Uses `httpx.Client` (synchronous, matching the `Resolver` interface)

### Modified file: `src/purl_resolver/settings_store.py`

Add to `AppSettings`:
```python
librariesio_enabled: bool = False
librariesio_api_key: str | None = None
```

### Modified file: `src/purl_resolver/router.py`

- `GET /api/v1/settings` → add `librariesio_enabled` and `token_set.librariesio_api_key: bool`
- `PATCH /api/v1/settings` → handle `librariesio_enabled` (bool) and `librariesio_api_key` (str|null)
  - `null` → clears the key
  - Empty string `""` → ignored (no change)
  - Non-empty string → validated via `validate_librariesio_key()`
  - Invalid key → `400 { "error": "invalid_token", "message": "Libraries.io API key is invalid" }`
- After settings save: re-resolve `app.state.resolvers` list based on new settings

**New validation function:**
```python
def validate_librariesio_key(api_key: str) -> bool:
    # GET https://libraries.io/api/platforms?api_key={key}
    # 200 → valid, 401/403 → invalid, error → assume valid (don't block save)
```

### Modified file: `src/purl_resolver/resolver/interface.py`

Add `name` property to the `Resolver` ABC:

```python
class Resolver(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def resolve(self, purl: str) -> Resolution: ...
```

`Purl2RepoResolver.name` → `"purl2repo"`
`LibrariesIoResolver.name` → `"libraries.io"`

### Modified file: `src/purl_resolver/resolver/purl2repo.py`

Add `name` property:

```python
class Purl2RepoResolver(Resolver):

    @property
    def name(self) -> str:
        return "purl2repo"
```

### Modified file: `src/purl_resolver/service.py`

In the resolver iteration loop (line 115), replace `resolver=resolver` with `resolver=r.name`:

```python
response = ResolveResponse(
    ...
    resolver=r.name,  # was: resolver=resolver
)
```

This ensures the DB `resolver` field reflects which resolver actually found the result, not the caller-provided parameter. The `resolver` parameter from the router is retained for backward compatibility but `r.name` takes precedence.

### Modified file: `src/purl_resolver/main.py`

In `lifespan()`:
```python
app.state.resolvers = [Purl2RepoResolver(...)]
settings = settings_store.load()
if settings.librariesio_enabled and settings.librariesio_api_key:
    app.state.resolvers.append(
        LibrariesIoResolver(api_key=settings.librariesio_api_key)
    )
```

### Modified file: `src/purl_resolver/templates/settings.html`

New card «Libraries.io Resolver»:
- Checkbox: «Enable libraries.io resolver»
- Password input: API key
- Status badge: «set» / «not set»
- Clear button
- Link to https://libraries.io/login
- Save button triggers PATCH to `/api/v1/settings`

### Unchanged files

- `sbom_enrichment.py` — uses `resolve_batch()` which works with the resolver list; no changes needed

## Error Handling

| Scenario | Behavior |
|---|---|
| libraries.io API timeout | Log warning, return `Resolution()` with warning |
| libraries.io returns 429 | Log warning, return `Resolution()` with warning |
| libraries.io returns 401/403 | Log warning, return `Resolution()` with warning |
| libraries.io returns 5xx | Log warning, return `Resolution()` with warning |
| Network unreachable | Log warning, return `Resolution()` with warning |
| Unknown PURL type | Return `Resolution()` with warning (no API call) |
| Invalid PURL | Raise `InvalidPurlError` (same as other resolvers) |

In all error cases, the resolver returns `Resolution()` without `repository_url`, so the chain continues to the next resolver (if any) or returns a result with warnings.

## Ecosystem Mapping

| PURL type | libraries.io platform |
|---|---|
| `cargo` | Cargo |
| `composer` | Packagist |
| `conda` | Conda |
| `cpan` | CPAN |
| `cran` | CRAN |
| `gem` | RubyGems |
| `generic` | GitHub |
| `golang` | Go |
| `hackage` | Hackage |
| `hex` | Hex |
| `maven` | Maven |
| `npm` | NPM |
| `nuget` | NuGet |
| `pub` | Pub |
| `pypi` | PyPI |
| `swift` | SwiftPM |

Unsupported PURL types return a warning without making an API call.

## Rate Limiting

- Minimum interval: 1 second between requests
- Implementation: `time.monotonic()` + `time.sleep()` (synchronous, matching the `Resolver` interface)
- Before each request: `time.sleep(max(0, self._min_interval - (time.monotonic() - self._last_request_time)))`
- libraries.io limit: 60 req/min with API key → 1 req/sec is well within limits
- Uses `httpx.Client` (synchronous HTTP client, already installed in the project)

## Testing Strategy

- **Unit test** for ecosystem mapping (all supported types + unknown type)
- **Integration test** with `httpx.MockTransport` (success, 401, 429, timeout)
- **Integration test** for rate limiting (verify minimum interval between requests using `time.monotonic` mock)
- **Integration test** for graceful degradation (error → Resolution with warning)
- **Integration test** for the resolver chain (purl2repo fails → libraries.io succeeds)
- **Test settings** persistence (enable/disable, API key save/clear/validate)
- Follow existing test patterns in `tests/`
