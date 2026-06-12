# HTTP Resolver Retry Design

## Problem

HTTP-based resolvers (`EcosystemsResolver`, `LibrariesIoResolver`) make no retry attempts when upstream returns a rate-limit response (HTTP 429), a timeout (`httpx.TimeoutException`), or a transient server error (5xx). A single failure causes immediate fallback to warnings, even though retrying after a short cooldown would likely succeed.

## Scope

- Only HTTP-based resolvers: `EcosystemsResolver` and `LibrariesIoResolver`
- `Purl2RepoResolver` is excluded — it uses a synchronous library via `asyncio.to_thread()` and cannot distinguish retryable errors
- The `Resolver` ABC interface (`resolve(purl) → Resolution`) remains unchanged — retry is an internal implementation detail

## Settings

Universal settings (shared across all HTTP resolvers), added to `AppSettings`:

| Key | Default | Min | Max | Description |
|---|---|---|---|---|
| `retry_max_attempts` | `3` | `1` | `10` | Maximum HTTP request attempts (including the first) |
| `retry_base_cooldown_seconds` | `5.0` | `0.5` | `120.0` | Base cooldown in seconds; actual wait = `cooldown × (attempt − 1)` (linear backoff) |

### SettingsUpdate

Same fields with `None` default and same bounds, exposed via `PATCH /api/v1/settings`.

### Settings UI

Two new input fields in `templates/settings.html` under a "Resolver Behaviour" section.

## Retryable Errors

| Condition | Retryable |
|---|---|
| `httpx.TimeoutException` | Yes |
| `httpx.HTTPStatusError` with status 429 | Yes |
| `httpx.HTTPStatusError` with status 5xx | Yes |
| `httpx.HTTPStatusError` with other status (400, 401, 403, 404) | No |
| `httpx.HTTPError` (network errors) | Yes |
| Any other exception | No |

## Module: `RetryHelper`

New file: `src/purl_resolver/resolver/retry.py`

### Types

```python
@dataclass
class RetryConfig:
    max_attempts: int = 3
    base_cooldown_seconds: float = 5.0


@dataclass
class RetryAttempt:
    attempt: int
    exception: Exception | None = None
    wait_seconds: float = 0.0
```

### RetryHelper

```python
class RetryHelper:
    def __init__(self, config: RetryConfig) -> None: ...

    async def execute[T](
        self,
        coroutine_factory: Callable[[], Awaitable[T]],
    ) -> T:
```

**Behaviour:**
1. First attempt executes immediately via `coroutine_factory()`
2. On retryable exception: wait `base_cooldown_seconds × (attempt_number - 1)`, then retry
3. On success: return response immediately
4. On non-retryable exception: re-raise immediately
5. After `max_attempts` retryable failures: re-raise the last exception

The resolver's existing `try/except` blocks catch the re-raised exception and convert it to `Resolution(warnings=[...])` — same as today. The only difference is that the exception only reaches the catch block after exhausting retries.

### Exception Classification

`RetryableErrorPolicy.is_retryable(exc)` — static method encapsulating the retryable-error table above.

## Resolver Changes

### EcosystemsResolver

- `__init__` accepts optional `retry_config: RetryConfig | None = None`
- Creates `self._retry = RetryHelper(retry_config or RetryConfig())`
- HTTP call wrapped: `response = await self._retry.execute(lambda: self._client.get(...))`

### LibrariesIoResolver

- Same pattern: accept `retry_config`, create `RetryHelper`, wrap HTTP call

### Factory (`factory.py`)

```python
retry_config = RetryConfig(
    max_attempts=app_settings.retry_max_attempts,
    base_cooldown_seconds=app_settings.retry_base_cooldown_seconds,
)
```

Passed to both `EcosystemsResolver` and `LibrariesIoResolver`. `Purl2RepoResolver` unchanged.

## Data Flow

```
Resolver.resolve(purl)
  └─ RetryHelper.execute(coroutine_factory)
       ├─ attempt 1: HTTP request
       │    ├─ success → return response
       │    ├─ non-retryable exception → re-raise
       │    └─ retryable exception → wait cooldown × 1
       ├─ attempt 2: HTTP request
       │    ├─ success → return response
       │    ├─ non-retryable exception → re-raise
       │    └─ retryable exception → wait cooldown × 2
       ├─ attempt 3: HTTP request
       │    ├─ success → return response
       │    └─ any exception → re-raise
       └─ re-raised exception caught by resolver's except block
            └─ return Resolution(purl, warnings=[...])
```

## Testing

- New unit tests: `tests/test_retry_helper.py`
  - Successful on first attempt
  - Retryable error on attempts 1..N-1, success on Nth
  - All attempts fail → re-raise after max_attempts
  - Non-retryable error → immediate re-raise
  - Cooldown respects `base_cooldown_seconds` linear growth
- Existing resolver tests: ensure retry integration does not break normal resolution
- No new e2e tests required (retry is invisible to callers)

## Files Changed

| File | Change |
|---|---|
| `src/purl_resolver/resolver/retry.py` | New — `RetryConfig`, `RetryHelper`, `RetryableErrorPolicy` |
| `src/purl_resolver/settings_store.py` | Add `retry_max_attempts`, `retry_base_cooldown_seconds` to `AppSettings` |
| `src/purl_resolver/routes/settings.py` | Add fields to `SettingsUpdate`, include in GET response |
| `src/purl_resolver/resolver/factory.py` | Build `RetryConfig`, pass to HTTP resolvers |
| `src/purl_resolver/resolver/ecosystems.py` | Accept `retry_config`, use `RetryHelper` |
| `src/purl_resolver/resolver/librariesio.py` | Accept `retry_config`, use `RetryHelper` |
| `templates/settings.html` | UI inputs for retry settings |
| `tests/test_retry_helper.py` | New — unit tests for retry logic |
| `specs/domains/purl-resolution.md` | Update Configuration table |
| `specs/architecture/layers.md` | Update Resolver Layer section |
