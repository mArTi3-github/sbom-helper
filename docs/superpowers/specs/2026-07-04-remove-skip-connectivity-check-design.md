# Remove Dead Code: Duplicate Connectivity Check in validate_url

## Problem

`skip_connectivity_check` is a parameter on `validate_url()`, `validate_url_with_retry()`, and `UrlValidationService.validate_url()`. In every production code path, it is passed as `True` (skipping the check). The only code path where it is `False` is in tests — meaning the parameter and the connectivity-check code block inside `validate_url()` are dead in production.

## Current Architecture

Connectivity checking exists at two levels:

1. **Gatekeeper** (`ensure_connectivity()` in `routes/resolve.py`) — one `_check_connectivity()` call at the start of each API endpoint. On failure → HTTP 503.
2. **Per-URL check** (inside `validate_url()`) — a second `_check_connectivity()` call that is always skipped in production via `skip_connectivity_check=True`.

The `_head_request()` call inside `validate_url()` already catches `httpx.RequestError` and returns `UrlValidationResult.NETWORK_ERROR`, which is the same result the connectivity check would produce. So even without the per-URL connectivity probe, a mid-request network failure is properly handled.

## Design Decision

1. Remove the `skip_connectivity_check` parameter and the associated connectivity-check code block from `validate_url()`, `validate_url_with_retry()`, and `UrlValidationService.validate_url()`.
2. Inline `_check_connectivity()` into `ensure_connectivity()` and remove `_check_connectivity()` — it has no other callers after the dead code removal. There is no need for two separate functions; `ensure_connectivity()` is the sole public connectivity-check function used by the route layer.

- `_check_connectivity()` and `ensure_connectivity()` remain unchanged — the gatekeeper at route level is the sole connectivity check.
- `_head_request()` serves as the fallback network-error handler inside `validate_url()`.

## Files Changed

### Source code

| File | Change |
|---|---|
| `src/purl_resolver/url_validator.py` | Remove `skip_connectivity_check`, `connectivity_url`, `connectivity_timeout` parameters from `validate_url()` and `validate_url_with_retry()`; remove the `if not skip_connectivity_check:` block from `validate_url()`; inline `_check_connectivity()` into `ensure_connectivity()` and remove `_check_connectivity()` |
| `src/purl_resolver/validation_service.py` | Remove `skip_connectivity_check` parameter from `UrlValidationService.validate_url()` |
| `src/purl_resolver/service.py` | Remove `skip_connectivity_check=True` from all 4 calls to `validate_url()`/`validate_url_with_retry()` |
| `src/purl_resolver/sbom_enrichment.py` | Remove `skip_connectivity_check=True` from both calls to `validate_url()`/`validate_url_with_retry()` |

### Tests

| File | Change |
|---|---|
| `tests/test_url_validator.py` | Remove `TestValidateUrlSkipConnectivity` class; remove `test_connectivity_probe_fails_returns_network_error` from `TestValidateUrl` |
| `tests/test_service_validation.py` | Remove `skip_connectivity_check=True` from 3 calls |
| `tests/test_sbom_integration.py` | Remove `skip_connectivity_check=True` from 1 call |

### Specs

| File | Change |
|---|---|
| `specs/domains/purl-resolution.md` | Remove `skip_connectivity_check` from function signatures in lines 159-160, 179 |

## Invariants Preserved

- Gatekeeper connectivity check at route level remains — each API request still runs `ensure_connectivity()` once
- Network errors during `_head_request()` still return `UrlValidationResult.NETWORK_ERROR`
- Rate-limit tracker is still properly reset on `_head_request()` network errors

## Open Questions

None — design is self-contained.