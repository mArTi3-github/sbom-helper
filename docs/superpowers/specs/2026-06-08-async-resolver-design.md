# Async Resolver Translation Design

## Problem Statement

При обработке SBOM файлов выполнение параллельных запросов через веб-интерфейс блокируется или происходит с большой задержкой. Причина: синхронные вызовы внутри async функций блокируют event loop FastAPI.

### Identified Blocking Points

| File | Line | Issue |
|---|---|---|
| `service.py` | 108 | `r.resolve(purl)` — sync call inside async function |
| `resolver/purl2repo.py` | 44 | `purl2repo_resolve()` — external sync library with HTTP calls |
| `resolver/ecosystems.py` | 39, 56 | `httpx.Client` (sync) — blocks for up to 15s |
| `resolver/librariesio.py` | 43, 68 | `httpx.Client` (sync) — blocks for up to 15s |
| `resolver/librariesio.py` | 95-99 | `time.sleep()` — blocks event loop for up to 1 second |

### Why This Blocks Parallel Requests

FastAPI processes all `async def` endpoints on a single event loop. When SBOM enrichment calls `resolve_batch()` → `asyncio.gather()` → 10 concurrent `resolve_purl()`, each calling synchronous `r.resolve()`, the event loop is blocked for the entire duration of HTTP requests. Other requests (Settings, DB admin) must wait.

## Solution: Full Async Translation

### Changes

| File | Change |
|---|---|
| `resolver/interface.py` | `resolve()` → `async def resolve()` |
| `resolver/purl2repo.py` | Wrap `purl2repo_resolve()` in `asyncio.to_thread()` |
| `resolver/ecosystems.py` | `httpx.Client` → `httpx.AsyncClient`, `resolve()` → async |
| `resolver/librariesio.py` | `httpx.Client` → `httpx.AsyncClient`, `time.sleep` → `asyncio.sleep`, `resolve()` → async |
| `service.py` | `r.resolve(purl)` → `await r.resolve(purl)` |
| Tests | Update mock resolve calls to async |

### Rate Limiting Preservation

- `LibrariesIoResolver._rate_limit_wait()` → `async def _rate_limit_wait()` with `asyncio.sleep()` instead of `time.sleep()`
- `_RateLimitTracker` in `url_validator.py` — already async-friendly, no changes needed
- Batch semaphore (`_BATCH_SEMAPHORE_LIMIT = 10`) — already async, preserved

### Architecture

```
Before (blocking):
┌─────────────────────────────────────────────────────────┐
│ Event Loop                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Request 1    │  │ Request 2    │  │ Request 3    │  │
│  │ (SBOM)       │  │ (Settings)   │  │ (DB Admin)   │  │
│  │              │  │              │  │              │  │
│  │ r.resolve()  │  │   WAITING    │  │   WAITING    │  │
│  │ [BLOCKED]    │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘

After (non-blocking):
┌─────────────────────────────────────────────────────────┐
│ Event Loop                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ Request 1    │  │ Request 2    │  │ Request 3    │  │
│  │ (SBOM)       │  │ (Settings)   │  │ (DB Admin)   │  │
│  │              │  │              │  │              │  │
│  │ await        │  │ Processing   │  │ Processing   │  │
│  │ r.resolve()  │  │              │  │              │  │
│  │ [I/O yield]  │  │              │  │              │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## Implementation Details

### 1. Resolver Interface (`resolver/interface.py`)

```python
class Resolver(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    async def resolve(self, purl: str) -> Resolution: ...
```

### 2. Purl2Repo Resolver (`resolver/purl2repo.py`)

External library `purl2repo` is synchronous and cannot be modified. Wrap in `asyncio.to_thread()`:

```python
async def resolve(self, purl: str) -> Resolution:
    try:
        result = await asyncio.to_thread(
            purl2repo_resolve,
            purl,
            timeout=self._timeout,
            use_cache=self._use_cache,
            strict=self._strict,
            no_network=self._no_network,
            cache_dir=self._cache_dir,
        )
    except UnsupportedEcosystemError as e:
        # ... error handling unchanged
```

### 3. Ecosystems Resolver (`resolver/ecosystems.py`)

Replace sync `httpx.Client` with `httpx.AsyncClient`:

```python
class EcosystemsResolver(Resolver):

    def __init__(self, api_key: str | None = None, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def resolve(self, purl: str) -> Resolution:
        # ... validation unchanged
        try:
            response = await self._client.get(_API_URL, params=params)
            response.raise_for_status()
        # ... error handling unchanged
```

### 4. Libraries.io Resolver (`resolver/librariesio.py`)

Replace sync client and blocking sleep:

```python
class LibrariesIoResolver(Resolver):

    def __init__(self, api_key: str, timeout: float = 15.0) -> None:
        self._api_key = api_key
        self._timeout = timeout
        self._min_interval = 1.0
        self._last_request_time = 0.0
        self._client = httpx.AsyncClient(timeout=timeout)

    async def resolve(self, purl: str) -> Resolution:
        # ... validation unchanged
        await self._rate_limit_wait()
        # ... HTTP call with await
        try:
            response = await self._client.get(url, params={"api_key": self._api_key})
            response.raise_for_status()
        # ... error handling unchanged

    async def _rate_limit_wait(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()
```

### 5. Service Layer (`service.py`)

Update call site to use `await`:

```python
for r in resolvers:
    try:
        resolution = await r.resolve(purl)
    except InvalidPurlError as e:
        return ResolveResult.err(400, "invalid_purl", str(e))
    # ... rest unchanged
```

### 6. Tests

Update test mocks to return async functions:

```python
class MockResolver(Resolver):
    async def resolve(self, purl: str) -> Resolution:
        return Resolution(purl=purl, repository_url="https://github.com/test/repo")
```

## Testing Strategy

1. **Unit tests**: Verify each resolver works correctly with async interface
2. **Integration tests**: Verify `resolve_batch()` processes multiple PURLs concurrently without blocking
3. **Manual test**: Run SBOM enrichment in one browser tab, access Settings/DB Admin in another tab — both should respond immediately

## Success Criteria

- [ ] Event loop is not blocked during resolver HTTP calls
- [ ] Multiple concurrent requests (SBOM + Settings + DB Admin) are processed in parallel
- [ ] Rate limiting for libraries.io (1 req/sec) is preserved
- [ ] Rate limit tracking in url_validator.py works correctly
- [ ] All existing tests pass
- [ ] No regression in SBOM enrichment functionality

## Out of Scope

- Connection pooling optimization for httpx.AsyncClient (future enhancement)
- Resolver timeout configuration per-resolver (current global timeout preserved)
- Caching strategy changes (purl2repo file cache unchanged)
