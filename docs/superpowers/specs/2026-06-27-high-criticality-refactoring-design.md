# High-Criticality Refactoring: Instance State, Exception Narrowing, UrlValidationService

## Scope

Three isolated high-criticality refactoring changes identified by architecture analysis. No behavioral changes. All existing tests must pass after each change.

---

### C1: `_RateLimitTracker` — Class State → Instance State

**Files:** `src/purl_resolver/url_validator.py`, `tests/test_url_validator.py`

**Problem:** `_RateLimitTracker` uses class-level `_count` and `_cooldown_until`. This is global mutable state shared across all concurrent async calls — unsafe without locking, prevents multiple trackers, and requires tests to directly mutate class attributes.

**Solution:** Convert to instance class with `asyncio.Lock`, create module-level singleton:

```python
class _RateLimitTracker:
    def __init__(self) -> None:
        self._count: int = 0
        self._cooldown_until: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()

    async def is_in_cooldown(self) -> bool: ...
    async def record_rate_limit(self) -> None: ...
    def reset(self) -> None: ...

_rate_limit_tracker = _RateLimitTracker()
```

- `validate_url()` calls `_rate_limit_tracker.is_in_cooldown()` / `.record_rate_limit()` / `.reset()`
- Test fixture calls `_rate_limit_tracker.reset()` instead of `_RateLimitTracker._count = 0`
- `test_rate_limit_cooldown_skips_validation` sets internal state via public method or instance attributes

**No changes to function signatures** of `validate_url()`, `validate_url_with_retry()`.

**Test implications:** The existing test `test_rate_limit_cooldown_skips_validation` (test_url_validator.py:122) sets cooldown state directly. With instance approach, it accesses `_rate_limit_tracker._count` and `_rate_limit_tracker._cooldown_until` directly — same pattern, just on the instance instead of the class. No need to go through `asyncio.Lock` for test setup.

---

### C2: Broad `except Exception` — Narrow to Specific Types

**Files:** `src/purl_resolver/url_validator.py`, `src/purl_resolver/purl_utils/__init__.py`, `src/purl_resolver/service.py`

**Principle:** Each `except` catches only the exception types known to occur in its try-block. Everything else propagates upwards (FastAPI returns 500 and logs it).

| Location | Current | Target | Rationale |
|----------|---------|--------|-----------|
| `purl_utils/__init__.py:51` `safe_normalize` | `except Exception: return purl` | `except (ValueError, PurlValidationError): return purl` | Only parse errors are expected |
| `url_validator.py:132` `_check_connectivity` | `except Exception: return False` | `except httpx.RequestError: return False` | httpx network errors only |
| `url_validator.py:185` `_git_probe` | `except Exception as e: return None` | `except (OSError, asyncio.TimeoutError) as e: return None` | Subprocess + timeout |
| `url_validator.py:209` `_svn_probe` | `except Exception as e: return None` | `except (OSError, asyncio.TimeoutError) as e: return None` | Subprocess + timeout |
| `url_validator.py:233` `_hg_probe` | `except Exception as e: return None` | `except (OSError, asyncio.TimeoutError) as e: return None` | Subprocess + timeout |
| `url_validator.py:275` `_fossil_probe_xfer` | `except Exception as e: return None` | `except httpx.RequestError as e: return None` | httpx transport errors only |
| `url_validator.py:303` `_fossil_probe_footer` | `except Exception as e: return None` | `except httpx.RequestError as e: return None` | httpx transport errors only |
| `url_validator.py:363` `validate_github_token` | `except Exception: return False` | `except (httpx.RequestError, ConnectionError): return False` | Network errors only |
| `url_validator.py:382` `validate_url` connectivity | `except Exception: return NETWORK_ERROR` | `except (httpx.RequestError, ConnectionError, OSError): return NETWORK_ERROR` | Network + DNS resolution |
| `url_validator.py:395` `validate_url` HEAD | `except Exception: return NETWORK_ERROR` | `except httpx.RequestError: return NETWORK_ERROR` | httpx errors only |
| `url_validator.py:417` `validate_url` VCS | `except Exception: return NETWORK_ERROR` | `except Exception: logger.warning(...); return NETWORK_ERROR` | Safety net with log |
| `service.py:73,78,106,165` | `except Exception: logger.warning(...)` | Keep `except Exception` with `exc_info=True` (already present) | Storage is best-effort; fatal errors logged, batch continues |
| `url_validator.py:445` `validate_url_with_retry` save | `except Exception: logger.warning(...)` | Keep `except Exception` with `exc_info=True` | Token persistence is best-effort |

The `_fossil_probe` function (line 308) is a thin dispatcher that calls `_fossil_probe_xfer` and `_fossil_probe_footer` — both already handle their own exceptions. No change needed at the dispatcher level.

---

### C3: Extract `UrlValidationService`

**Files:** `src/purl_resolver/validation_service.py` (new), `src/purl_resolver/service.py`, `src/purl_resolver/sbom_enrichment.py`, `src/purl_resolver/main.py`, `tests/test_service_validation.py`, `tests/test_sbom_integration.py`

**Problem:** URL validation logic is inlined in three places: `_validate_cached_url` (service.py:33-82), `resolve_purl` resolver loop (service.py:126-147), and `sbom_enrichment.py`. Each place duplicates `validate_url_with_retry()` call setup and retry logic. `_validate_cached_url` is a `@staticmethod` that duplicates `self` fields as parameters.

**Solution:** New class `UrlValidationService` with single responsibility — take a URL and return validation result. Cooldown decision stays in callers.

```python
class UrlValidationService:
    def __init__(self, settings_store: SettingsStore) -> None:
        self._settings_store = settings_store

    async def validate_url(
        self,
        url: str,
        timeout: int,
        github_token: str | None = None,
        skip_connectivity_check: bool = False,
    ) -> UrlValidationOutput:
        """Validate URL with retry, using settings from _settings_store."""
        return await validate_url_with_retry(
            url, timeout,
            github_token=github_token,
            settings_store=self._settings_store,
            skip_connectivity_check=skip_connectivity_check,
        )
```

**Impact on consumers:**

1. **`PurlResolutionService`:**
   - Constructor: add `validation_service: UrlValidationService` param, remove `settings_store`
   - `_validate_cached_url`: change from `@staticmethod` to instance method, use `self._storage`, `self._validation_service`
   - Extract `_is_within_cooldown(cached) -> bool` from `_validate_cached_url`
   - `resolve_purl()` inline validation: replace with `self._validation_service.validate_url()`

2. **`SbomEnrichmentPipeline`:**
   - Constructor: accept `UrlValidationService` instead of raw function import

3. **`main.py` / `router.py`:** Instantiate `UrlValidationService` and pass to `PurlResolutionService` and `SbomEnrichmentPipeline`

**No changes to:** `validate_url()` or `validate_url_with_retry()` module-level functions in `url_validator.py` — they remain as internal implementation.

---

## Testing Strategy

After each change: `.venv/bin/pytest tests/ -v`

- C1: existing tests pass after updating fixture to `_rate_limit_tracker.reset()`; cooldown test accesses `_rate_limit_tracker._count` directly
- C2: existing tests pass after updating `mock_head.side_effect = Exception(...)` → `mock_head.side_effect = httpx.RequestError(...)` in test_url_validator.py:88,235 (the code now only catches httpx.RequestError, not bare Exception)
- C3: existing tests pass; create `UrlValidationService` in conftest or inline fixtures

## Anti-Patterns Avoided

- Do NOT change function signatures of exported API functions (`validate_url`, `validate_url_with_retry`)
- Do NOT add abstractions without clear consumers
- Do NOT change storage layer or resolver chain behavior
- Do NOT add runtime dependencies or configuration changes