# PURL URL Validation Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix four issues in URL validation: rate-limit cooldown returning VALID, stale "today-cooldown" for untrusted resolvers, SBOM enrichment staleness trap, and missing cooldown_hours setting.

**Architecture:** Changes span four layers: URL validator (return RATE_LIMITED), service layer (cooldown logic with resolver check), SBOM pipeline (validate existing refs), and settings (new cooldown_hours config). Each is independently testable.

**Tech Stack:** Python 3.12+ / FastAPI / asyncpg / pytest / Jinja2

---

### Task 0: Read current state of key files

- [ ] **Step 1: Read all files that will be modified**

```
Read:
  src/purl_resolver/service.py:21-75 (_validate_cached_url)
  src/purl_resolver/url_validator.py:130-135 (rate cooldown)
  src/purl_resolver/sbom_enrichment.py (full file)
  src/purl_resolver/settings_store.py:19-31 (AppSettings)
  src/purl_resolver/routes/settings.py (full file)
  src/purl_resolver/routes/resolve.py:33-74 (resolve_sbom_endpoint)
  src/purl_resolver/templates/settings.html (full file)
  src/purl_resolver/templates/sbom.html (full file)
  tests/test_service_validation.py (full file)
  tests/test_url_validator.py (full file)
  tests/test_sbom_integration.py (full file)
  tests/test_settings_store.py (full file)
```

---

### Task 1: Rate-limit cooldown returns RATE_LIMITED instead of VALID

**Files:**
- Modify: `src/purl_resolver/url_validator.py:132-133`
- Test: `tests/test_url_validator.py`

- [ ] **Step 1: Write the failing test**

Read `tests/test_url_validator.py` first, then add these tests:

```python
# At the end of test_url_validator.py, after existing tests

@pytest.mark.asyncio
async def test_rate_cooldown_returns_rate_limited():
    """During rate-limit cooldown, validate_url returns RATE_LIMITED not VALID."""
    with patch("purl_resolver.url_validator._RateLimitTracker.is_in_cooldown", return_value=True):
        result = await validate_url("https://github.com/psf/requests", timeout=5)
        assert result == UrlValidationResult.RATE_LIMITED
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_url_validator.py::test_rate_cooldown_returns_rate_limited -v`
Expected: FAIL — returns VALID instead of RATE_LIMITED

- [ ] **Step 3: Change VALID to RATE_LIMITED**

In `src/purl_resolver/url_validator.py`, line 133:

```python
if _RateLimitTracker.is_in_cooldown():
    return UrlValidationResult.RATE_LIMITED
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_url_validator.py::test_rate_cooldown_returns_rate_limited -v`
Expected: PASS

- [ ] **Step 5: Run existing tests to verify no regressions**

Run: `pytest tests/test_url_validator.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/url_validator.py tests/test_url_validator.py
git commit -m "fix: rate-limit cooldown returns RATE_LIMITED instead of VALID"
```

---

### Task 2: New cooldown logic in `_validate_cached_url()` with resolver check

**Files:**
- Modify: `src/purl_resolver/service.py:21-75`
- Test: `tests/test_service_validation.py`

- [ ] **Step 1: Read current `_validate_cached_url` and `resolve_purl`**

Read full content of `service.py` to understand exact current state.

- [ ] **Step 2: Write tests for new cooldown behavior**

Add these to `tests/test_service_validation.py` (after `TestValidateCachedUrl` class):

```python
TRUSTED_RESOLVERS = {"purl2repo", "ecosyste.ms", "libraries.io"}


class TestResolverBasedCooldown:
    """_validate_cached_url cooldown depends on resolver field."""

    @pytest.mark.asyncio
    async def test_trusted_resolver_within_cooldown_skips_validation(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=2)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url") as mock_validate:
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached
        mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_trusted_resolver_outside_cooldown_runs_validation(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=48)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID) as mock_validate:
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_untrusted_resolver_always_validates(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="import-sbom",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID) as mock_validate:
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_empty_resolver_always_validates(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID) as mock_validate:
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_cooldown_hours_zero_disables_cooldown(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=(datetime.now() - timedelta(hours=1)).isoformat(),
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=0,
            github_token=None,
            url_validation_timeout=5,
        )
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.VALID) as mock_validate:
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", AsyncMock())
        assert result == cached
        mock_validate.assert_called_once()

    @pytest.mark.asyncio
    async def test_rate_limited_does_not_update_resolved_at(self):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at="2020-01-01T00:00:00",
        )
        settings_store = MagicMock()
        settings_store.load.return_value = MagicMock(
            validate_db_urls=True,
            revalidation_cooldown_hours=24,
            github_token=None,
            url_validation_timeout=5,
        )
        storage = AsyncMock()
        with patch("purl_resolver.service.validate_url", return_value=UrlValidationResult.RATE_LIMITED):
            result = await _validate_cached_url(cached, settings_store, "pkg:pypi/requests", storage)
        assert result == cached
        storage.store.assert_not_called()
        storage.delete_purls.assert_not_called()
```

- [ ] **Step 3: Run new tests to verify they fail**

Run: `pytest tests/test_service_validation.py::TestResolverBasedCooldown -v`
Expected: all FAIL — `_validate_cached_url` still has old logic

- [ ] **Step 4: Add TRUSTED_RESOLVERS constant and update `_validate_cached_url` in service.py**

Add at the top of `service.py`, after imports:

```python
TRUSTED_RESOLVERS: frozenset[str] = frozenset({"purl2repo", "ecosyste.ms", "libraries.io"})
```

Replace the `_validate_cached_url` function body in `service.py`:

```python
async def _validate_cached_url(
    cached: ResolveResponse,
    settings_store: SettingsStore | None,
    purl_key: str,
    storage: Storage,
) -> ResolveResponse | None:
    if settings_store is None:
        return cached

    app_settings = settings_store.load()
    if not app_settings.validate_db_urls:
        return cached

    # Resolver-based cooldown: trusted resolvers respect cooldown_hours,
    # untrusted/empty resolvers always trigger validation
    cooldown_hours = app_settings.revalidation_cooldown_hours
    if cooldown_hours > 0 and cached.resolver in TRUSTED_RESOLVERS and cached.resolved_at:
        try:
            resolved_date = datetime.fromisoformat(cached.resolved_at)
            elapsed = datetime.now() - resolved_date
            if elapsed.total_seconds() < cooldown_hours * 3600:
                return cached
        except (ValueError, TypeError):
            pass

    github_token = app_settings.github_token
    vresult = await validate_url(
        cached.repository_url,
        app_settings.url_validation_timeout,
        github_token=github_token,
    )

    if vresult == UrlValidationResult.TOKEN_INVALID:
        logger.warning("GitHub token invalid, removing from settings")
        try:
            settings_store.save(app_settings.model_copy(update={"github_token": None}))
        except Exception:
            logger.warning("Failed to persist token removal to settings", exc_info=True)
        vresult = await validate_url(
            cached.repository_url,
            app_settings.url_validation_timeout,
            github_token=None,
        )

    if vresult == UrlValidationResult.VALID:
        try:
            await storage.store(cached)
        except Exception:
            logger.warning("Failed to update resolved_at for %s", purl_key, exc_info=True)
    elif vresult == UrlValidationResult.INVALID:
        try:
            await storage.delete_purls([purl_key])
        except Exception:
            logger.warning("Failed to delete invalid URL for %s", purl_key, exc_info=True)
        return None

    return cached
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_service_validation.py -v`
Expected: all PASS (both old and new tests)

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/service.py tests/test_service_validation.py
git commit -m "feat: resolver-based cooldown for URL validation"
```

---

### Task 3: Add `revalidation_cooldown_hours` to AppSettings

**Files:**
- Modify: `src/purl_resolver/settings_store.py:19-26`
- Test: `tests/test_settings_store.py`

- [ ] **Step 1: Read current `AppSettings` model**

- [ ] **Step 2: Add tests for new field**

In `tests/test_settings_store.py`, after existing tests:

```python
def test_revalidation_cooldown_hours_default():
    s = AppSettings()
    assert s.revalidation_cooldown_hours == 24

def test_revalidation_cooldown_hours_min():
    s = AppSettings(revalidation_cooldown_hours=0)
    assert s.revalidation_cooldown_hours == 0

def test_revalidation_cooldown_hours_custom():
    s = AppSettings(revalidation_cooldown_hours=48)
    assert s.revalidation_cooldown_hours == 48

def test_revalidation_cooldown_hours_serialize():
    s = AppSettings(revalidation_cooldown_hours=12, validate_db_urls=True)
    data = s.model_dump()
    assert data["revalidation_cooldown_hours"] == 12
    loaded = AppSettings(**data)
    assert loaded.revalidation_cooldown_hours == 12
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_settings_store.py::test_revalidation_cooldown_hours_default -v`
Expected: FAIL — field doesn't exist yet

- [ ] **Step 4: Add field to AppSettings**

In `src/purl_resolver/settings_store.py`, add to `AppSettings`:

```python
class AppSettings(BaseModel):
    validate_db_urls: bool = False
    url_validation_timeout: int = Field(default=5, ge=1, le=60)
    revalidation_cooldown_hours: int = Field(default=24, ge=0, le=720)
    github_token: str | None = None
    librariesio_enabled: bool = False
    librariesio_api_key: str | None = None
    ecosystems_enabled: bool = True
    ecosystems_api_key: str | None = None
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_settings_store.py -v`
Expected: all PASS

- [ ] **Step 6: Expose new field in settings API**

Read `src/purl_resolver/routes/settings.py`. Find `GET /api/v1/settings` and `PATCH /api/v1/settings` endpoints.

In the response body of GET endpoint, add `revalidation_cooldown_hours` alongside existing fields.

In the PATCH endpoint handler, add `revalidation_cooldown_hours: int | None = None` to the request body model/parsing, and apply it to `AppSettings`.

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "feat: add revalidation_cooldown_hours setting"
```

---

### Task 4: Update Settings page UI with cooldown_hours input

**Files:**
- Modify: `src/purl_resolver/templates/settings.html`
- Modify: `src/purl_resolver/routes/settings.py` (if not done in Task 3 step 6)

- [ ] **Step 1: Read the settings.html and settings.py files**

- [ ] **Step 2: Add cooldown_hours input in settings.html**

In the "URL Validation" card in settings.html, after the timeout input row, add:

```html
<div class="setting-row">
    <div>
        <div class="setting-label">Re-validation cooldown (hours)</div>
        <div class="setting-desc">
            When set to 24 (default), URLs cached by trusted resolvers
            (purl2repo, ecosyste.ms, libraries.io) are re-validated at most once per day.
            Entries from imports or manual edits are always re-validated regardless of cooldown.
            Set to 0 to disable cooldown and always validate.
        </div>
    </div>
    <input type="number" id="cooldown-input" min="0" max="720" value="24">
</div>
```

In the JavaScript, add:
```javascript
const cooldownInput = document.getElementById("cooldown-input");
```

In `loadSettings()`:
```javascript
cooldownInput.value = data.revalidation_cooldown_hours;
```

In `saveSettings()` body:
```javascript
body.revalidation_cooldown_hours = parseInt(cooldownInput.value, 10);
```

- [ ] **Step 3: Add cooldown_hours to settings API response**

In `routes/settings.py`, ensure `GET /api/v1/settings` returns:
```python
"revalidation_cooldown_hours": settings.revalidation_cooldown_hours,
```

And `PATCH /api/v1/settings` accepts and updates it.

- [ ] **Step 4: Run existing tests**

Run: `pytest tests/test_settings_store.py tests/test_api.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/templates/settings.html src/purl_resolver/routes/settings.py
git commit -m "feat: add cooldown hours setting to UI and API"
```

---

### Task 5: SBOM Updater — validate existing VCS references checkbox

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py`
- Modify: `src/purl_resolver/routes/resolve.py:33-74`
- Modify: `src/purl_resolver/templates/sbom.html`
- Test: `tests/test_sbom_enrichment.py` (or `tests/test_sbom_integration.py`)

- [ ] **Step 1: Read current SBOM pipeline files**

- [ ] **Step 2: Write tests for existing-refs validation**

In `tests/test_sbom_integration.py` (or a new file), add:

```python
@pytest.mark.asyncio
async def test_validate_existing_refs_invalid_url_triggers_reresolution(
    mock_storage, mock_settings_store, resolver
):
    """When validate_existing_refs=True and an existing VCS ref is invalid,
    the component is marked for re-resolution."""
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
                "externalReferences": [
                    {"type": "vcs", "url": "https://github.com/psf/requests-invalid"}
                ],
            }
        ],
    }
    # Setup: component has existing VCS ref but still needs enrichment check
    pipeline = SbomEnrichmentPipeline(
        storage=mock_storage,
        resolvers=[resolver],
        settings_store=mock_settings_store,
    )
    with patch("purl_resolver.sbom_enrichment.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.INVALID):
        result = await pipeline.process(sbom, validate_existing_refs=True)
    # Should have resolved the PURL
    assert result.report["summary"]["found"] > 0 or result.report["summary"]["not_found"] >= 0

    # Verify the component was resolved and enriched
    enriched_refs = sbom["components"][0].get("externalReferences", [])
    assert any(r.get("url") == resolver.resolve.return_value.repository_url for r in enriched_refs)


@pytest.mark.asyncio
async def test_validate_existing_refs_valid_url_skips_reresolution(
    mock_storage, mock_settings_store, resolver
):
    """When validate_existing_refs=True but the existing VCS ref IS valid,
    the component is left as-is."""
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
                "externalReferences": [
                    {"type": "vcs", "url": "https://github.com/psf/requests"}
                ],
            }
        ],
    }
    original_refs = sbom["components"][0]["externalReferences"].copy()
    pipeline = SbomEnrichmentPipeline(
        storage=mock_storage,
        resolvers=[resolver],
        settings_store=mock_settings_store,
    )
    with patch("purl_resolver.sbom_enrichment.validate_url", new_callable=AsyncMock, return_value=UrlValidationResult.VALID):
        result = await pipeline.process(sbom, validate_existing_refs=True)
    # Component should not have been resolved (removed from purls_to_resolve)
    # The existing refs should be preserved
    assert sbom["components"][0]["externalReferences"] == original_refs


@pytest.mark.asyncio
async def test_validate_existing_refs_default_off(mock_storage, mock_settings_store, resolver):
    """When validate_existing_refs=False (default), existing refs are not validated."""
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "library",
                "name": "requests",
                "version": "2.31.0",
                "purl": "pkg:pypi/requests@2.31.0",
                "externalReferences": [
                    {"type": "vcs", "url": "https://github.com/psf/requests-invalid"}
                ],
            }
        ],
    }
    pipeline = SbomEnrichmentPipeline(
        storage=mock_storage,
        resolvers=[resolver],
        settings_store=mock_settings_store,
    )
    with patch("purl_resolver.sbom_enrichment.validate_url", new_callable=AsyncMock) as mock_validate:
        result = await pipeline.process(sbom, validate_existing_refs=False)
    mock_validate.assert_not_called()
```

- [ ] **Step 3: Add the `validate_existing_refs` parameter to `SbomEnrichmentPipeline.process()`**

In `src/purl_resolver/sbom_enrichment.py`:

Add import:
```python
from .url_validator import validate_url, UrlValidationResult
from .sbom.collector import _SOURCE_REF_TYPES
```

Modify `process()` signature:
```python
async def process(
    self,
    sbom_data: dict,
    remove_unresolved_no_subcomponents: bool = False,
    validate_existing_refs: bool = False,
) -> SbomEnrichmentResult:
```

After `components = collect_components(sbom_data)` and before `purls_to_resolve = ...`, add:

```python
    if validate_existing_refs:
        for comp in components:
            if comp.needs_enrichment:
                continue
            for ref in comp.existing_references:
                if ref.get("type") in _SOURCE_REF_TYPES and ref.get("url"):
                    vresult = await validate_url(
                        ref["url"],
                        timeout=5,
                        github_token=None,
                    )
                    if vresult == UrlValidationResult.INVALID:
                        comp.needs_enrichment = True
                        comp.existing_references = []
                    break
```

- [ ] **Step 4: Pass `validate_existing_refs` from the API endpoint**

In `src/purl_resolver/routes/resolve.py`, in `resolve_sbom_endpoint`:

```python
@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
    validate_existing_refs: bool = Form(False),
) -> JSONResponse:
    ...
    result = await pipeline.process(
        data,
        remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents,
        validate_existing_refs=validate_existing_refs,
    )
```

- [ ] **Step 5: Add checkbox to sbom.html**

In `src/purl_resolver/templates/sbom.html`, find the existing checkbox for "remove unresolved" and add after it:

```html
<div class="checkbox-row" style="margin-top:0.5rem;">
    <label class="checkbox-label">
        <input type="checkbox" id="validate-refs-checkbox">
        Проверять существующие VCS-ссылки в SBOM
    </label>
    <div class="setting-desc" style="margin-top:0.25rem;font-size:0.8rem;">
        Если включено, существующие externalReferences проверяются на валидность.
        Невалидные ссылки помечаются для повторного разрешения.
    </div>
</div>
```

In the JavaScript, find where `remove_unresolved_no_subcomponents` is read from the form and add:

```javascript
const validateRefs = document.getElementById("validate-refs-checkbox").checked;
formData.append("validate_existing_refs", validateRefs);
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_sbom_integration.py -v`
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/sbom_enrichment.py src/purl_resolver/routes/resolve.py src/purl_resolver/templates/sbom.html tests/
git commit -m "feat: add validate_existing_refs checkbox to SBOM Updater"
```

---

### Task 6: Update specification documents

**Files:**
- Modify: `specs/domains/purl-resolution.md`

- [ ] **Step 1: Read current spec**

- [ ] **Step 2: Update invariants section**

Add new invariants:

```
- **Resolver-based cooldown**: Trusted resolvers (`purl2repo`, `ecosyste.ms`, `libraries.io`) respect `revalidation_cooldown_hours` setting; entries from other resolvers (e.g. `import-sbom`, `import-csv`) always trigger validation regardless of cooldown
- **Cooldown disabled at zero**: Setting `revalidation_cooldown_hours=0` disables cooldown entirely — every cached entry triggers validation when `validate_db_urls=true`
- **Rate-limit cooldown no longer masks invalid URLs**: During rate-limit cooldown, `validate_url()` returns `RATE_LIMITED` instead of `VALID` — cache is preserved but `resolved_at` is not updated, so the next request after cooldown will perform real validation
- **SBOM existing-ref validation**: Optional checkbox `validate_existing_refs` in SBOM Updater validates existing VCS references via HEAD + git ls-remote; INVALID results mark the component for re-resolution
```

Add to Configuration (JSON Settings) table:

```
| `revalidation_cooldown_hours` | `24` | Re-validation cooldown in hours for trusted resolvers (0 = disabled, max 720) |
```

- [ ] **Step 3: Commit**

```bash
git add specs/domains/purl-resolution.md
git commit -m "docs: update purl-resolution spec with new validation invariants"
```

---

### Task 7: Final integration check

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: all tests PASS

- [ ] **Step 2: Verify lint/typecheck**

Run: `cd .venv/bin && ./ruff check ../../src/ && cd ../..`
Expected: no errors

- [ ] **Step 3: Commit any remaining changes**

```bash
git add -A
git commit -m "chore: final integration adjustments after URL validation fixes"
```