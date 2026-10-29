# ecosyste.ms Resolver Design

## Problem

CSV import from ecosyste.ms loads data once. For packages not in the local database, a live query is needed to find repository URLs during SBOM enrichment.

## Solution

Add an ecosyste.ms resolver as a fallback in the resolver chain, between purl2repo and libraries.io. The resolver queries the ecosyste.ms Packages API in real time to find repository URLs for unresolved PURLs.

## API

```
GET https://packages.ecosyste.ms/api/v1/packages/lookup?purl={purl}&api_key={optional_key}
```

**Response:** JSON array of package objects. First element contains:
- `repository_url` — repository URL (e.g. `https://github.com/psf/requests`)
- `registry_url` — package registry URL (e.g. `https://pypi.org/project/requests/`)
- `homepage` — project homepage (e.g. `https://requests.readthedocs.io`)
- `ecosystem` — package ecosystem (e.g. `pypi`)

**Empty result:** `[]` — package not found.

**Authentication:** API key is optional. API works without key (tested 2026-06-05). Key may provide higher rate limits. API does not distinguish between valid and invalid keys — validation is not possible.

## Resolver Chain

```
purl2repo → ecosyste.ms → libraries.io
```

- purl2repo: primary resolver, always enabled
- ecosyste.ms: fallback, enabled via Settings toggle (default: on, no API key required)
- libraries.io: last resort, enabled via Settings toggle + requires API key

## URL Selection Logic

```python
def select_repository_url(package_data: dict) -> str | None:
    candidates = [
        package_data.get('repository_url', ''),
        package_data.get('registry_url', ''),
        package_data.get('homepage', ''),
    ]

    # Pass 1: prefer GitHub URLs
    for url in candidates:
        if not url or 'repos.ecosyste.ms' in url:
            continue
        if 'github.com' in url:
            return url

    # Pass 2: any non-ecosyste.ms URL
    for url in candidates:
        if url and 'repos.ecosyste.ms' not in url:
            return url

    return None
```

## Architecture

### New file: `src/purl_resolver/resolver/ecosystems.py`

```python
class EcosystemsResolver(Resolver):
    def __init__(self, api_key: str | None = None, timeout: float = 15.0): ...

    @property
    def name(self) -> str:  # → "ecosyste.ms"

    def resolve(self, purl: str) -> Resolution: ...
```

**`resolve()` flow:**
1. Validate PURL via `purl_utils.validate()` (same as libraries.io)
2. HTTP GET `https://packages.ecosyste.ms/api/v1/packages/lookup?purl={purl}`
3. Include `api_key` in query params if provided
4. Parse response:
   - Empty array `[]` → `Resolution(warnings=["No package found on ecosyste.ms"])`
   - Non-empty → extract URL via `select_repository_url()`
5. Return `Resolution` with `repository_url`, `repository_kind="vcs"`, `confidence="medium"`, `evidence=["ecosyste.ms:{ecosystem}/{name}"]`

**Error handling (graceful degradation):**
- `httpx.TimeoutException` → `Resolution(warnings=["ecosyste.ms timeout for {purl}"])`
- `httpx.HTTPStatusError` → `Resolution(warnings=["ecosyste.ms error {status} for {purl}"])`
- `httpx.HTTPError` → `Resolution(warnings=["ecosyste.ms network error for {purl}: {exc}"])`

All errors return `Resolution` without `repository_url`, allowing the chain to continue.

### Modified: `src/purl_resolver/settings_store.py`

Add to `AppSettings`:
```python
ecosystems_enabled: bool = True
ecosystems_api_key: str | None = None
```

### Modified: `src/purl_resolver/router.py`

**`_rebuild_resolvers()`:**
```python
resolvers = [Purl2RepoResolver(...)]
if app_settings.ecosystems_enabled:
    resolvers.append(EcosystemsResolver(api_key=app_settings.ecosystems_api_key))
if app_settings.librariesio_enabled and app_settings.librariesio_api_key:
    resolvers.append(LibrariesIoResolver(...))
```

**`GET /api/v1/settings`** — add `ecosystems_enabled` and `ecosystems_api_key` to token_set.

**`PATCH /api/v1/settings`** — handle `ecosystems_enabled` and `ecosystems_api_key`. No API key validation (unlike libraries.io).

### Modified: `src/purl_resolver/templates/settings.html`

Add new card "eCosyste.ms Resolver":
- Toggle: enable/disable (default: on)
- API key input (optional, password field)
- Status badge: "set" / "not set"
- Clear key button
- Description: "Live query to ecosyste.ms API for repository URL lookup. Works without API key. Key is optional for higher rate limits."

Pattern matches existing libraries.io card.

## Settings

### Environment Variables

No new environment variables. ecosyste.ms resolver is configured entirely through JSON settings.

### JSON Settings (`data/settings.json`)

| Key | Default | Description |
|---|---|---|
| `ecosystems_enabled` | `true` | Enable ecosyste.ms as a fallback resolver |
| `ecosystems_api_key` | `null` | Optional API key for higher rate limits |

## Testing

### Unit tests: `tests/test_ecosystems_resolver.py`

- `TestEcosystemsMapping` — PURL type to ecosystem mapping
- `TestResolverName` — name returns `"ecosyste.ms"`
- `TestResolveSuccess` — mock httpx.Client, verify repository_url extraction
- `TestResolveUrlSelection` — priority logic: GitHub > other; skip repos.ecosyste.ms
- `TestResolveNoPackage` — empty array `[]` → warning
- `TestResolveErrors` — timeout, 4xx, 5xx, network errors → warning
- `TestApiKeyPassed` — key included in request params
- `TestApiKeyOptional` — request works without key

### E2E test: `tests/e2e/test_ecosystems.py`

```python
pytestmark = pytest.mark.skipif(
    os.environ.get("SKIP_E2E") == "1",
    reason="Set SKIP_E2E=1 to skip e2e tests (require network)",
)

class TestE2EEcosystemsResolver:
    def test_resolve_real_request(self):
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/requests")
        assert result.repository_url == "https://github.com/psf/requests"
        assert result.confidence == "medium"

    def test_resolve_unknown_package(self):
        r = EcosystemsResolver(timeout=15.0)
        result = r.resolve("pkg:pypi/nonexistent-pkg-xyz")
        assert result.repository_url is None
        assert len(result.warnings) > 0
```

Pattern matches `tests/e2e/test_postgres.py`. Service unavailability causes test skip, not failure.

## Configuration

- **Timeout:** 15 seconds (same as purl2repo default)
- **Rate limiting:** Not implemented (API handles it server-side)
- **Caching:** Automatic via existing storage layer (PostgresCache)

## File Changes

### Create
- `src/purl_resolver/resolver/ecosystems.py`
- `tests/test_ecosystems_resolver.py`
- `tests/e2e/test_ecosystems.py`
- `docs/adr/0005-ecosyste-ms-as-fallback-resolver.md`

### Modify
- `src/purl_resolver/settings_store.py` — add `ecosystems_enabled`, `ecosystems_api_key`
- `src/purl_resolver/router.py` — update `_rebuild_resolvers()`, `GET/PATCH /api/v1/settings`
- `src/purl_resolver/templates/settings.html` — add ecosyste.ms settings card
- `specs/domains/purl-resolution.md` — add configuration fields
- `specs/architecture/layers.md` — add EcosystemsResolver to resolver layer

### Unchanged
- `resolver/interface.py` — Resolver ABC unchanged
- `resolver/librariesio.py` — no changes
- `resolver/purl2repo.py` — no changes
- `service.py` — no changes (resolver chain managed via `app.state.resolvers`)
