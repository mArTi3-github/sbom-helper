# HTTP Redirect Resolution for URL Validation — Design

## Problem Summary

When a repository URL returns HTTP 301 (or any 3xx redirect), the current URL validator transparently follows the redirect (via httpx `follow_redirects=True`) but **discards the final URL**. The original (redirecting) URL continues to be stored in the database, returned to users, and embedded in enriched SBOMs — causing every subsequent validation cycle to repeat the same redirect chain.

Three contexts are affected:
1. **Validate URLs from local Database** (`Settings` → `validate_db_urls`) — re-checks cached entries
2. **PURL Resolver** — returns resolved URL to the user
3. **SBOM Updater** — checks existing VCS references in SBOM (`validate_existing_refs`)

## Solution: Propagate Final URL Through Validation Pipeline

Introduce a `UrlValidationOutput` dataclass that carries both the validation result and the effective URL after all redirects. All consumers use the final URL instead of the original.

### A. New data type — `UrlValidationOutput`

**File:** `src/purl_resolver/url_validator.py`

```python
@dataclass
class UrlValidationOutput:
    result: UrlValidationResult
    final_url: str | None = None
```

| Scenario | `result` | `final_url` |
|---|---|---|
| URL not http/https | `INVALID` | `None` |
| Rate-limit cooldown active | `RATE_LIMITED` | `None` |
| Connectivity check failed | `NETWORK_ERROR` | `None` |
| HEAD request exception | `NETWORK_ERROR` | `None` |
| HEAD succeeded → status checks | depends on status | `str(resp.url)` |
| HEAD succeeded → git ls-remote | `VALID` / `INVALID` / `NETWORK_ERROR` | `str(resp.url)` |

`final_url` is `str(resp.url)` from httpx after all redirects. If no redirect occurred, `resp.url` equals the requested URL — then `final_url == url`.

### B. Changes to `validate_url()`

**Flow:**

1. Keep existing checks (scheme, rate-limit cooldown, connectivity)
2. After `resp = await _head_request(url, ...)`: capture `final_url = str(resp.url)`. Log redirect if `final_url != url`
3. Pass `final_url` to `_git_ls_remote()` instead of original `url` (the redirect target is what needs git validation)
4. Return `UrlValidationOutput(result, final_url)` for successful requests, `UrlValidationOutput(result, None)` when HEAD didn't execute

**Return type change:** `UrlValidationResult` → `UrlValidationOutput`

### C. Changes to `validate_url_with_retry()`

**Return type change:** `UrlValidationResult` → `UrlValidationOutput`

- First call: `validate_url(url, ...)` → `UrlValidationOutput`
- If `TOKEN_INVALID` + retry: `validate_url(url, ...)` → new `UrlValidationOutput`
- Return last `UrlValidationOutput` (includes `final_url` from the retry call, which is more relevant)

### D. Changes to `service.py` — `_validate_cached_url()`

```python
output = await validate_url_with_retry(cached.repository_url, ...)
if output.result == UrlValidationResult.VALID:
    new_url = output.final_url or cached.repository_url
    if new_url != cached.repository_url:
        cached.repository_url = new_url  # update URL in cache entry
    await storage.store(cached)          # update resolved_at
elif output.result == UrlValidationResult.INVALID:
    await storage.delete_purls([purl_key])
    return None
# NETWORK_ERROR / RATE_LIMITED: return cached as-is, resolved_at NOT updated
return cached
```

### E. Changes to `service.py` — `resolve_purl()` (fresh URL from resolver)

```python
output = await validate_url_with_retry(repo_url, ...)
if output.result == UrlValidationResult.INVALID:
    continue  # skip to next resolver
effective_url = output.final_url or repo_url
response = ResolveResponse(
    repository_url=effective_url,
    ...
)
```

For `NETWORK_ERROR` / `RATE_LIMITED`: `output.final_url` may be available (HEAD succeeded before rate-limit detection) — use it if set, even though validation was inconclusive. This avoids storing a redirecting URL.

### F. Changes to `sbom_enrichment.py`

```python
output = await validate_url_with_retry(ref["url"], ...)
if output.result == UrlValidationResult.INVALID:
    comp.needs_enrichment = True
    comp.existing_references = []
elif output.final_url and output.final_url != ref["url"]:
    ref["url"] = output.final_url  # update ref URL even on NETWORK_ERROR/RATE_LIMITED
```

The ref URL update applies for any non-INVALID result because the redirect fact (detected via HEAD) is independent of the git ls-remote result.

## Design Decisions

### All 3xx → final URL, without distinguishing 301/302/307

Reasoning:
- Every redirect (even "temporary") causes unnecessary HTTP round-trips on re-validation
- VCS URLs almost never use 302 for legitimate temporary redirects
- Next validation cycle (after `revalidation_cooldown_hours`) will detect any changes

### `git ls-remote` on final URL

Reasoning: the redirect target is what the consumer will clone/fetch. Validating the target ensures the stored URL is immediately usable without a redirect hop.

### `final_url=None` when HEAD didn't execute

Clean semantics: consumers test `output.final_url and output.final_url != original` to decide whether to update. When `None`, no redirect information is available.

## Invariants

- `validate_url()` and `validate_url_with_retry()` never raise — always return `UrlValidationOutput`
- `final_url` equals the input URL when no redirect occurred (redirect chain of length 0)
- `final_url` is `None` only when HEAD wasn't executed (scheme error, cooldown, connectivity failure, HEAD exception)
- `_git_ls_remote()` receives the resolved final URL, not the original
- Cache entries are updated with the final URL only on `VALID` result
- SBOM references are updated with the final URL on any non-INVALID result (including `NETWORK_ERROR`/`RATE_LIMITED`)
- Fresh resolver results use the final URL for any non-INVALID result

## Files Changed

| File | Change |
|------|--------|
| `src/purl_resolver/url_validator.py` | New `UrlValidationOutput` dataclass; `validate_url()` + `validate_url_with_retry()` return `UrlValidationOutput`; capture `resp.url`; pass final URL to `_git_ls_remote()` |
| `src/purl_resolver/service.py` | Update imports; `_validate_cached_url()` and `resolve_purl()` use `output.final_url` |
| `src/purl_resolver/sbom_enrichment.py` | Update imports; use `output.final_url` to update ref URLs |
| `tests/test_url_validator.py` | Update for new return type; add tests for redirect capture and git ls-remote on final URL |
| `tests/test_service_validation.py` | Update for new return type; add tests for URL update on redirect |
| `tests/test_sbom_integration.py` | Update for new return type |
| `specs/domains/purl-resolution.md` | Update invariants for redirect handling |
| `specs/architecture/layers.md` | No changes expected |

## Testing Strategy

### Unit tests — `test_url_validator.py`

- `validate_url()` returns `UrlValidationOutput` (type check)
- When HEAD succeeds without redirect: `final_url == input_url`
- When HEAD follows redirect: `final_url == redirect_target`
- When scheme is not http/https: `final_url is None`
- When rate-limit cooldown: `final_url is None`
- When connectivity fails: `final_url is None`
- `_git_ls_remote` called with final URL (via mock assertion)

### Unit tests — `test_service_validation.py`

- `_validate_cached_url()`: VALID + redirect → `cached.repository_url` updated
- `_validate_cached_url()`: VALID + no redirect → `cached.repository_url` unchanged
- `_validate_cached_url()`: NETWORK_ERROR / RATE_LIMITED → URL not updated
- `resolve_purl()`: VALID + redirect → `ResolveResponse.repository_url` is final URL

### Unit tests — `test_sbom_integration.py`

- `validate_existing_refs=True` + VALID + redirect → `ref["url"]` updated in SBOM
- `validate_existing_refs=True` + VALID + no redirect → `ref["url"]` unchanged
- `validate_existing_refs=True` + RATE_LIMITED + redirect → `ref["url"]` updated (redirect detected before rate limit)
- `validate_existing_refs=True` + INVALID → component marked for re-resolution, no URL update