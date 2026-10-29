# Low-Severity Architecture Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate 4 low-severity architectural issues: dead code, I/O at import time, hardcoded operational values, and dead conditions.

**Architecture:** Four independent cleanup tasks, ordered by dependency (test removals first, then dead code removals, then config additions). Tasks 1 and 2 have no dependencies on each other.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, Vue 3, TypeScript

---

### Task 1: Remove SPA probing from module-level I/O (#9)

**Files:**
- Modify: `src/purl_resolver/main.py:76-89`
- Modify: `tests/test_main.py:57-78`
- Modify: `tests/test_sbom_integration.py:35-52`

**Interfaces:**
- Consumes: `lifespan()` function in `main.py`
- Produces: SPA mounted conditionally inside `lifespan()` (Docker path only), no more `SPA_DIR` module-level variable

- [ ] **Step 1: Edit `main.py` — remove `_find_spa_dir()`, move SPA mount into `lifespan`**

```python
# Remove lines 76-89 entirely
# In lifespan(), after app.state.resolution_service = ... add:
    spa_dir = pathlib.Path("/app/frontend/dist")
    if spa_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(spa_dir), html=True), name="spa")
        logger.info("Serving SPA from %s", spa_dir)
```

The final state of `main.py` should remove the `SPA_DIR = _find_spa_dir()` and `if SPA_DIR is not None: app.mount(...)` block. The class `SPAStaticFiles` stays at module level.

- [ ] **Step 2: Edit `test_sbom_integration.py` — remove SPA mounting and `TestSbomUpdaterPage`**

Remove lines 35-39 from the `client()` fixture:
```python
    from purl_resolver.main import _find_spa_dir, SPAStaticFiles
    spa_dir = _find_spa_dir()
    if spa_dir is not None:
        test_app.mount("/", SPAStaticFiles(directory=str(spa_dir), html=True), name="spa")
```

Remove the entire `TestSbomUpdaterPage` class (lines 44-52).

- [ ] **Step 3: Edit `test_main.py` — remove `TestFindSpaDir`**

Remove the entire `TestFindSpaDir` class (lines 57-78).

- [ ] **Step 4: Run tests to verify nothing is broken**

Run: `.venv/bin/pytest tests/ -x -q --tb=short`
Expected: All tests pass (fewer tests, but no failures).

---

### Task 2: Remove dead code `ServiceTokens` (#11)

**Files:**
- Modify: `src/purl_resolver/settings_store.py:14-16,36-37`
- Modify: `tests/test_settings_store.py:8,66-86`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: cleaner `AppSettings` without `service_tokens()` method

- [ ] **Step 1: Edit `settings_store.py` — remove `ServiceTokens` dataclass and `service_tokens()` method**

```python
# Remove lines 14-17:
# @dataclass
# class ServiceTokens:
#     github_token: str | None = None

# Remove lines 36-37:
#     def service_tokens(self) -> ServiceTokens:
#         return ServiceTokens(github_token=self.github_token)
```

- [ ] **Step 2: Edit `test_settings_store.py` — remove `TestServiceTokens` and `TestAppSettingsServiceTokens`**

Remove the `TestServiceTokens` class (lines 66-73) and `TestAppSettingsServiceTokens` class (lines 76-96). Keep `TestAppSettingsDefaults` (it tests other defaults).

Also remove `ServiceTokens` from the import on line 8:
```python
from purl_resolver.settings_store import AppSettings, SettingsStore
```

- [ ] **Step 3: Run tests**

Run: `.venv/bin/pytest tests/test_settings_store.py -x -q --tb=short`
Expected: All remaining tests pass.

---

### Task 3: Remove dead `isinstance(str)` condition in `postgres.py` (#12)

**Files:**
- Modify: `src/purl_resolver/storage/postgres.py:86-91`

**Interfaces:**
- Consumes: nothing from other tasks
- Produces: cleaner `store()` method

- [ ] **Step 1: Edit `postgres.py:86-91` — remove dead isinstance checks**

Replace:
```python
                result.evidence
    if isinstance(result.evidence, str)
    else json.dumps(result.evidence),
    result.warnings
    if isinstance(result.warnings, str)
    else json.dumps(result.warnings),
```

With:
```python
                json.dumps(result.evidence),
                json.dumps(result.warnings),
```

- [ ] **Step 2: Run tests**

Run: `.venv/bin/pytest tests/ -x -q --tb=short`
Expected: All tests pass.

---

### Task 4: Make 4 operational values configurable via `AppSettings` + UI (#10)

**Files:**
- Modify: `src/purl_resolver/settings_store.py` — add 4 fields to `AppSettings`
- Modify: `src/purl_resolver/routes/settings.py` — add fields to `SettingsUpdate` and response serializers
- Modify: `src/purl_resolver/service.py` — use configurable `batch_semaphore_limit`
- Modify: `src/purl_resolver/url_validator.py` — accept configurable `connectivity_url`, `connectivity_timeout`, `rate_limit_cooldown`
- Modify: `frontend/src/types/api.ts` — add new fields to `SettingsResponse` and `SettingsUpdate`
- Modify: `frontend/src/views/Settings.vue` — add UI controls
- Modify: `frontend/src/views/Settings.test.ts` — add default values for new fields
- Modify: `tests/test_settings_store.py` — add tests for new defaults

**Interfaces:**
- Consumes: results from Task 2 (cleaned `AppSettings`)
- Produces: 4 new configurable parameters exposed via API + UI

- [ ] **Step 1: Add 4 fields to `AppSettings` in `settings_store.py`**

```python
    batch_semaphore_limit: int = Field(default=10, ge=1, le=100)
    connectivity_url: str = Field(default="https://github.com")
    connectivity_timeout: int = Field(default=2, ge=1, le=30)
    rate_limit_cooldown: int = Field(default=60, ge=1, le=600)
```

- [ ] **Step 2: Add fields to `SettingsUpdate` in `routes/settings.py`**

```python
    batch_semaphore_limit: int | None = Field(None, ge=1, le=100)
    connectivity_url: str | None = None
    connectivity_timeout: int | None = Field(None, ge=1, le=30)
    rate_limit_cooldown: int | None = Field(None, ge=1, le=600)
```

- [ ] **Step 3: Add fields to response of `get_settings` and `update_settings` in `routes/settings.py`**

In both `get_settings` and `update_settings` response dicts, add:
```python
        "batch_semaphore_limit": app_settings.batch_semaphore_limit,
        "connectivity_url": app_settings.connectivity_url,
        "connectivity_timeout": app_settings.connectivity_timeout,
        "rate_limit_cooldown": app_settings.rate_limit_cooldown,
```

- [ ] **Step 4: Update `service.py` — use configurable `batch_semaphore_limit`**

In `resolve_batch()` (line 210), replace:
```python
semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)
```
With:
```python
batch_limit = self._settings_store.load().batch_semaphore_limit if self._settings_store else _BATCH_SEMAPHORE_LIMIT
semaphore = asyncio.Semaphore(batch_limit)
```

- [ ] **Step 5: Update `url_validator.py` — accept configurable connectivity params**

Modify `validate_url()` signature to accept optional parameters:
```python
async def validate_url(
    url: str,
    timeout: int,
    github_token: str | None = None,
    skip_connectivity_check: bool = False,
    connectivity_url: str | None = None,
    connectivity_timeout: int | None = None,
    rate_limit_cooldown: int | None = None,
) -> UrlValidationOutput:
```

Update `_check_connectivity()` calls to pass these through. The key change:
- `_check_connectivity(github_token)` becomes `_check_connectivity(github_token=github_token, url=connectivity_url, timeout=connectivity_timeout)`
- `_check_connectivity` signature changes to accept `url` and `timeout` params, falling back to module constants when None
- In `_check_vcs` and others there are no hardcoded values to change

For `_RateLimitTracker.record_rate_limit()`, accept optional `cooldown` parameter:
```python
async def record_rate_limit(self, cooldown: int | None = None) -> None:
    cooldown = cooldown or _RATE_LIMIT_COOLDOWN
    ...
    self._cooldown_until = time.time() + cooldown
```

And in `validate_url`, on line 399, pass `rate_limit_cooldown`:
```python
await _rate_limit_tracker.record_rate_limit(cooldown=rate_limit_cooldown)
```

Also update `validate_url_with_retry()` to accept and forward the same parameters.

- [ ] **Step 6: Update `frontend/src/types/api.ts`**

Add to `SettingsResponse`:
```typescript
  batch_semaphore_limit: number
  connectivity_url: string
  connectivity_timeout: number
  rate_limit_cooldown: number
```

Add to `SettingsUpdate`:
```typescript
  batch_semaphore_limit?: number
  connectivity_url?: string
  connectivity_timeout?: number
  rate_limit_cooldown?: number
```

- [ ] **Step 7: Update `frontend/src/views/Settings.vue`**

Add new refs:
```typescript
const batchSemaphoreLimit = ref(10)
const connectivityUrl = ref('https://github.com')
const connectivityTimeout = ref(2)
const rateLimitCooldown = ref(60)
```

Add to `loadSettings()`:
```typescript
    batchSemaphoreLimit.value = data.batch_semaphore_limit
    connectivityUrl.value = data.connectivity_url
    connectivityTimeout.value = data.connectivity_timeout
    rateLimitCooldown.value = data.rate_limit_cooldown
```

Add a new card block in the template (after "Resolver Behaviour" card):
```html
      <div class="card">
        <div class="card-title">Network & Performance</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Batch concurrency limit</div>
            <div class="setting-desc">
              Maximum number of parallel PURL resolution requests in a batch (1–100). Default: 10.
            </div>
          </div>
          <input type="number" v-model.number="batchSemaphoreLimit" min="1" max="100" @change="debouncedAutoSave({ batch_semaphore_limit: batchSemaphoreLimit })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Connectivity probe URL</div>
            <div class="setting-desc">
              Target URL used to check internet access before URL validation. Set to empty to disable the probe.
            </div>
          </div>
          <input type="text" v-model="connectivityUrl" @blur="debouncedAutoSave({ connectivity_url: connectivityUrl || undefined })" class="txt-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Connectivity probe timeout (seconds)</div>
            <div class="setting-desc">
              Timeout for the connectivity HEAD request (1–30 seconds). Default: 2.
            </div>
          </div>
          <input type="number" v-model.number="connectivityTimeout" min="1" max="30" @change="debouncedAutoSave({ connectivity_timeout: connectivityTimeout })" class="num-input">
        </div>
        <div class="setting-row">
          <div>
            <div class="setting-label">Rate-limit cooldown (seconds)</div>
            <div class="setting-desc">
              How long to pause URL validation after consecutive rate-limited responses (1–600 seconds). Default: 60.
            </div>
          </div>
          <input type="number" v-model.number="rateLimitCooldown" min="1" max="600" @change="debouncedAutoSave({ rate_limit_cooldown: rateLimitCooldown })" class="num-input">
        </div>
      </div>
```

- [ ] **Step 8: Add `.txt-input` CSS class in `Settings.vue`**

Add after `.num-input` CSS block:
```css
.txt-input {
  width: 240px;
  padding: 0.5rem;
  border: 1px solid var(--color-input-border);
  border-radius: var(--border-radius);
  font-size: 0.9rem;
}
.txt-input:focus {
  outline: none;
  border-color: var(--color-primary);
}
```

- [ ] **Step 9: Update `frontend/src/views/Settings.test.ts`**

Add new fields to `defaultSettings`:
```typescript
  batch_semaphore_limit: 10,
  connectivity_url: 'https://github.com',
  connectivity_timeout: 2,
  rate_limit_cooldown: 60,
```

- [ ] **Step 10: Add tests for new settings defaults in `test_settings_store.py`**

In `TestAppSettingsDefaults`:
```python
    def test_batch_semaphore_limit_default(self):
        s = AppSettings()
        assert s.batch_semaphore_limit == 10

    def test_connectivity_url_default(self):
        s = AppSettings()
        assert s.connectivity_url == "https://github.com"

    def test_connectivity_timeout_default(self):
        s = AppSettings()
        assert s.connectivity_timeout == 2

    def test_rate_limit_cooldown_default(self):
        s = AppSettings()
        assert s.rate_limit_cooldown == 60
```

- [ ] **Step 11: Run all tests**

Run: `.venv/bin/pytest tests/ -x -q --tb=short`
Expected: All tests pass.

Run frontend tests (if available):
```bash
cd frontend && npx vitest run --reporter=verbose 2>/dev/null || echo "Frontend tests not configured or failed"
```