# JSON Indent Setting — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add configurable JSON indent (1/2/4 spaces) setting for SBOM download and images list download.

**Architecture:** New field `json_indent` in backend `AppSettings` → exposed via existing `GET/PATCH /api/v1/settings` → synced to Pinia store → passed as param to `downloadJson()`.

**Tech Stack:** Python/Pydantic (backend), Vue 3/Pinia/TypeScript (frontend)

## Global Constraints

- Default value: `4`
- Valid values: `1`, `2`, `4`
- No new API endpoints — reuse existing settings API
- Follow existing patterns (same as `log_level` setting)

---

### Task 1: Backend model + API route

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `src/purl_resolver/routes/settings.py`
- Test: `tests/test_settings_store.py`

**Interfaces:**
- Produces: `AppSettings.json_indent: int` (Pydantic field, default=4, ge=1, le=4)
- Produces: GET/PATCH responses include `"json_indent": int`

- [x] **Verify service is running**
  Ensure all background processes required for the project are active.
- [ ] **Add field to AppSettings**

  In `src/purl_resolver/settings_store.py:13`, after existing fields add:
  ```python
  json_indent: int = Field(default=4, ge=1, le=4)
  ```

- [ ] **Add field to SettingsUpdate + response**

  In `src/purl_resolver/routes/settings.py:30`, after `rate_limit_cooldown` add:
  ```python
  json_indent: int | None = Field(None, ge=1, le=4)
  ```

  In GET handler (`routes/settings.py:61`), add to returned dict:
  ```python
  "json_indent": app_settings.json_indent,
  ```

  In PATCH handler (`routes/settings.py:87`), add to returned dict:
  ```python
  "json_indent": updated.json_indent,
  ```

- [ ] **Verify with existing tests**

  Run: `bash -c "cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_settings_store.py tests/test_main.py -v"`

  Expected: all pass. New field is optional and doesn't break existing tests.

---

### Task 2: Frontend types + Pinia store

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/useSettingsStore.ts`

**Interfaces:**
- Consumes: `"json_indent"` from API response
- Produces: `SettingsResponse.json_indent: number`, `SettingsUpdate.json_indent?: number`, `store.jsonIndent: Ref<number>`

- [ ] **Add to SettingsResponse and SettingsUpdate**

  In `frontend/src/types/api.ts`, add to `SettingsResponse`:
  ```ts
  json_indent: number
  ```

  Add to `SettingsUpdate`:
  ```ts
  json_indent?: number
  ```

- [ ] **Add to Pinia store**

  In `frontend/src/stores/useSettingsStore.ts`, after `rateLimitCooldown`:
  ```ts
  const jsonIndent = ref(4)
  ```

  In `load()`, after `rateLimitCooldown.value = data.rate_limit_cooldown`:
  ```ts
  jsonIndent.value = data.json_indent
  ```

  Add `jsonIndent` to the `return` block.

---

### Task 3: downloadJson utility + view wiring

**Files:**
- Modify: `frontend/src/composables/useDownload.ts`
- Modify: `frontend/src/views/SbomUpdater.vue`
- Modify: `frontend/src/views/ImagesListConverter.vue`

**Interfaces:**
- Consumes: `store.jsonIndent`
- Produces: `downloadJson(data, filename, indent=4)` — third param

- [ ] **Update downloadJson signature**

  In `frontend/src/composables/useDownload.ts`, change line 1 from:
  ```ts
  export function downloadJson(data: unknown, filename: string): void {
  ```
  to:
  ```ts
  export function downloadJson(data: unknown, filename: string, indent: number = 4): void {
  ```

  Replace `JSON.stringify(data, null, 2)` with:
  ```ts
  const blob = new Blob([JSON.stringify(data, null, indent)], { type: 'application/json' })
  ```

- [ ] **Update SbomUpdater.vue**

  Add import after line 131:
  ```ts
  import { useSettingsStore } from '../stores/useSettingsStore'
  ```

  Replace `downloadResult()` body (lines 226-229):
  ```ts
  function downloadResult() {
    if (!enrichedSbom.value || !selectedFile.value) return
    const store = useSettingsStore()
    downloadJson(enrichedSbom.value, selectedFile.value.name.replace(/\.json$/, '') + '_enriched.json', store.jsonIndent)
  }
  ```

- [ ] **Update ImagesListConverter.vue**

  Add import after line 80:
  ```ts
  import { useSettingsStore } from '../stores/useSettingsStore'
  ```

  Replace `downloadResult()` body (lines 121-124):
  ```ts
  function downloadResult() {
    if (!imagesListData.value || !selectedFile.value) return
    const store = useSettingsStore()
    downloadJson(imagesListData.value, selectedFile.value.name.replace(/\.json$/, '') + '_images_list.json', store.jsonIndent)
  }
  ```

---

### Task 4: Settings page UI

**Files:**
- Modify: `frontend/src/views/Settings.vue`

- [ ] **Add JSON Format card to template**

  After the "Logging" card (`</div>` closing the card before `<div v-if="toast"`), add:
  ```vue
      <div class="card">
        <div class="card-title">JSON Format</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">JSON indent size</div>
            <div class="setting-desc">
              Number of spaces used when indenting JSON in downloaded files (SBOM, Images List).
            </div>
          </div>
          <select v-model.number="jsonIndent" @change="debouncedAutoSave({ json_indent: jsonIndent })" class="select-input">
            <option :value="1">1 space</option>
            <option :value="2">2 spaces</option>
            <option :value="4">4 spaces</option>
          </select>
        </div>
      </div>
  ```

- [ ] **Add jsonIndent to store import**

  In the store destructuring (around lines 254-260), add `jsonIndent`:
  ```ts
  const {
    validateDbUrls, urlValidationTimeout, revalidationCooldownHours,
    retryMaxAttempts, retryBaseCooldownSeconds, logLevel,
    librariesioEnabled, ecosystemsEnabled, ecosystemsMaxRequestsPerSecond,
    batchSemaphoreLimit, connectivityUrl, connectivityTimeout, rateLimitCooldown,
    tokenSet, loading, jsonIndent,
  } = storeToRefs(store)
  ```

---

### Task 5: E2E verification

- [ ] **Check backend serves the new field**

  Run: `curl -s http://localhost:8000/api/v1/settings | python3 -m json.tool | grep json_indent`

  Expected: `"json_indent": 4`

- [ ] **Check frontend compiles**

  Run: `cd frontend && npx vue-tsc --noEmit 2>&1 | head -20`

  Expected: no TypeScript errors.

- [ ] **Check frontend build**

  Run: `cd frontend && npx vite build 2>&1 | tail -5`

  Expected: build succeeds.