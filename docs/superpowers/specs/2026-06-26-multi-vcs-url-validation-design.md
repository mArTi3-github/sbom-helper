# Multi-VCS URL Validation — Design

## Problem Summary

Currently `src/purl_resolver/url_validator.py` probes URLs only with `git ls-remote`. The Service Layer relies on this single VCS check to decide whether a cached repository URL is still valid (`VALID`), has become invalid (`INVALID`), or couldn't be determined (`NETWORK_ERROR`). This works well for git hosts (GitHub, GitLab, Bitbucket, Codeberg, etc.) but **mis-classifies valid Subversion, Mercurial, and Fossil repositories as `INVALID`**, causing them to be deleted from the cache and rejected by the resolver chain.

The reference implementation in `.misc/addictional_materials/sbom-checker/sbom_utils.py::check_repo` demonstrates the canonical solution: probe git → svn → hg → fossil sequentially with early-exit on first success.

This change replaces the single `_git_ls_remote()` helper with a unified multi-VCS probe that all existing consumers (single PURL resolve, cached URL revalidation, SBOM existing-ref validation) call transparently through `validate_url()` / `validate_url_with_retry()`.

## Solution: Unified `_check_vcs()` Replacing `_git_ls_remote()`

### A. New function — `_check_vcs()` in `url_validator.py`

**File:** `src/purl_resolver/url_validator.py`

```python
async def _check_vcs(
    url: str,
    timeout: int,
    github_token: str | None = None,
) -> bool | None:
    """Probe whether URL points to a git, svn, hg, or fossil repository.

    Runs four probes sequentially with early-exit on first success.
    Returns:
        True  — at least one VCS tool confirmed the URL is its repo type.
        False — no VCS tool confirmed; at least one definitively said "not a repo".
        None  — all probes were inconclusive (timeout, transport error).
                Caller should treat as network error / preserve cache.
    """
```

| Probe | Command | Success | "Not a repo" (False) | Transport error (None) |
|---|---|---|---|---|
| git | `git ls-remote --exit-code <url>` | exit 0 | exit ≠ 0 with "not found" / "does not exist" in stderr | timeout / other exception |
| svn | `svn ls <url>` | exit 0 | exit ≠ 0 | timeout / exception |
| hg | `hg identify <url>` | exit 0 | exit ≠ 0 | timeout / exception |
| fossil | `httpx.AsyncClient.get(url, follow_redirects=True)` | status 200 AND footer regex match | status 200 without footer, or non-200 | timeout / connection error |

**Fossil detection regex** (case-insensitive):

```python
r'footer"?>\s*this page was generated in about\s*(\d+\.\d+)s\s*by\s*fossil'
```

**Aggregation rule:**

```python
if any probe returned True:    return True       # confirmed VCS repo
if any probe returned False:   return False      # definitively not any VCS type
return None                                       # all probes hit transport errors
```

**GitHub token:** only the git probe rewrites `github.com` URLs to `oauth2:token@` form (current behavior preserved). svn, hg, and fossil probes ignore the token.

### B. Changes to `validate_url()`

Replace the call:

```python
git_result = await _git_ls_remote(final_url, timeout, github_token=github_token)
```

with:

```python
vcs_result = await _check_vcs(final_url, timeout, github_token=github_token)
```

The mapping from `vcs_result` to `UrlValidationResult` is identical to the existing mapping from `git_result`:

| `vcs_result` | `UrlValidationResult` |
|---|---|
| `True` | `VALID` |
| `False` | `INVALID` |
| `None` | `NETWORK_ERROR` |

### C. Removal of `_git_ls_remote()`

`_git_ls_remote()` is a private helper (prefix `_`). It is replaced by `_check_vcs()` and removed. No external callers exist — search confirms only `validate_url()` uses it.

### D. No changes to public API

- `validate_url()` signature unchanged (only internal implementation differs)
- `validate_url_with_retry()` signature unchanged
- `service.py` and `sbom_enrichment.py` need **zero** changes — they already call `validate_url_with_retry()` which transparently benefits from the new probe.

### E. Docker image changes — add `subversion` and `mercurial`

**File:** `Dockerfile` (both `dev` and `prod` stages, lines 16–18 and 46–48):

```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends git subversion mercurial openssl && \
    rm -rf /var/lib/apt/lists/*
```

- `git` is already installed — unchanged.
- `subversion` provides the `svn` binary.
- `mercurial` provides the `hg` binary.
- `fossil` requires no binary (HTTP-based detection).

## Design Decisions

### Sequential probing with early-exit, not parallel

**Reasoning:**
- Matches the reference implementation in `sbom-checker`
- Simpler error handling and timeout management
- Avoids hammering a single remote host with 4 simultaneous probes
- Early-exit means most URLs only run 1–2 probes in practice

### Full timeout per probe (not shared budget)

**Reasoning:**
- Worst case ≈ 4 × `url_validation_timeout` (240s) for a URL that is none of the 4 VCS types
- For VCS-matching URLs, only 1 probe runs (early-exit) — latency identical to current behavior
- Matches sbom-checker's `SP_TIMEOUT = 60` per call
- Predictable for users — each probe gets the configured timeout

### Aggregation returns `None` when all probes are uncertain (key deviation from sbom-checker)

sbom-checker's `check_repo()` collapses every failure into `False`. In sbom-helper this would be catastrophic:

- `service.py::_validate_cached_url` calls `storage.delete_purls([purl_key])` on `INVALID`
- `service.py::resolve_purl` skips to the next resolver on `INVALID`

If all 4 probes time out (transient network issue), sbom-checker would return `False` → URL gets deleted from cache / resolver chain moves on. Our aggregation returns `None` → cache preserved, resolver chain keeps current result. This protects against cascading cache loss during network outages.

### GitHub token only affects git probe

The git probe is the only one that supports authenticated requests via `oauth2:token@` URL rewriting (git's native authentication mechanism). svn, hg, and fossil have different auth mechanisms that are out of scope for this change.

### `fossil` uses HTTP GET (not HEAD)

The fossil detection regex matches a string in the HTML body. `HEAD` returns only headers — no body. The reference uses `requests.get` for the same reason; we use `httpx.AsyncClient.get`.

### No new settings

The algorithm is unconditional — always runs all 4 probes when a URL reaches `_check_vcs`. This matches the "single unified algorithm" requirement. The `validate_db_urls` toggle already controls whether `_check_vcs` is invoked at all.

## Invariants

- **`_check_vcs()` never raises** — every probe is wrapped in `try/except` and converted to `True`/`False`/`None`
- **Early-exit on first success** — if git probe returns `True`, svn/hg/fossil probes do not run
- **Aggregation rule**: `True` wins; else `False` wins over `None`
- **Subprocess timeouts are non-fatal** — `asyncio.TimeoutError` is treated as `None` and logged; never raised to the caller
- **Other subprocess exceptions are non-fatal** — wrapped in `try/except`, logged as warning, treated as `None`
- **GitHub token rewriting is git-only** — only the git probe receives authenticated URLs
- **Docker image provides VCS tools** — `git`, `subversion`, `mercurial` are installed in both `dev` and `prod` stages
- **Fossil requires no binary** — uses `httpx.AsyncClient` only
- **`validate_url()` and `validate_url_with_retry()` signatures unchanged** — public API stays the same
- **No changes in `service.py` or `sbom_enrichment.py`** — they call the same `validate_url_with_retry()` and get the new behavior transparently

## Files Changed

| File | Change |
|------|--------|
| `src/purl_resolver/url_validator.py` | Add `_check_vcs()`; remove `_git_ls_remote()`; replace its call in `validate_url()` |
| `Dockerfile` | Add `subversion` and `mercurial` to `apt-get install` in both `dev` and `prod` stages |
| `tests/test_url_validator.py` | Update existing tests (if any reference `_git_ls_remote`); add tests for `_check_vcs` |
| `tests/test_vcs_check.py` (new) | Unit tests for `_check_vcs()` covering all 4 probes and aggregation rules |
| `specs/domains/purl-resolution.md` | Update URL Validator section; add invariants for multi-VCS validation |
| `specs/architecture/layers.md` | Update URL Validator responsibility description |
| `CONTEXT.md` | Update `URL Validator` term; optionally add `VcsCheck` term |
| `docs/superpowers/specs/2026-06-26-multi-vcs-url-validation-design.md` | This design doc |

## Testing Strategy

### Unit tests — `tests/test_vcs_check.py` (new)

Mock `asyncio.create_subprocess_exec` (for git/svn/hg) and `httpx.AsyncClient` (for fossil):

| Test | Setup | Expected |
|---|---|---|
| `test_git_success_returns_true` | git exit 0 | `True` |
| `test_svn_success_after_git_fail` | git "not found", svn exit 0 | `True` |
| `test_hg_success_after_git_svn_fail` | git + svn fail, hg exit 0 | `True` |
| `test_fossil_success_after_git_svn_hg_fail` | git + svn + hg fail, fossil HTTP 200 + regex | `True` |
| `test_all_probes_fail_returns_false` | all 4 probes definitively say "not a repo" | `False` |
| `test_all_probes_timeout_returns_none` | all 4 probes hit `asyncio.TimeoutError` | `None` |
| `test_partial_timeout_with_success_returns_true` | git timeout, svn succeeds | `True` |
| `test_fossil_non_200_returns_false` | fossil HTTP 404 | `False` (after earlier probes) |
| `test_fossil_200_no_footer_returns_false` | fossil HTTP 200, body lacks regex | `False` |
| `test_fossil_redirect_followed` | fossil URL responds with redirect | `follow_redirects=True` enabled |
| `test_no_shell_injection` | URL with shell metacharacters | subprocess called with list args, no `shell=True` |
| `test_github_token_used_for_git_only` | github_token set, URL is github.com | git probe gets oauth2 form; svn/hg/fossil don't |
| `test_aggregation_false_wins_over_none` | git timeout (None), svn "not repo" (False), hg timeout (None), fossil timeout (None) | `False` (at least one definitive False present) |
| `test_all_probes_uncertain_returns_none` | all 4 probes timeout (None) | `None` (no definitive False present) |

### Integration tests — extend existing test files

- `tests/test_url_validator.py`: verify `validate_url()` now delegates to `_check_vcs` (mock assertion)
- `tests/test_service_validation.py`: verify `_validate_cached_url()` correctly handles `True`/`False`/`None` from `_check_vcs` (no behavior change for service layer, just new code path)
- `tests/test_sbom_integration.py`: verify SBOM existing-ref validation uses `_check_vcs` for svn/hg/fossil URLs

### Manual verification checklist (end-to-end)

1. Build Docker image with new dependencies (`subversion`, `mercurial`)
2. Start container; confirm `git`, `svn`, `hg` are present in PATH
3. Resolve a PURL with a known svn URL → expect successful resolution
4. Resolve a PURL with a known hg URL → expect successful resolution
5. Resolve a PURL with a known fossil URL → expect successful resolution
6. Resolve a PURL pointing to a non-VCS URL → expect `repository_url: null` (not crash)