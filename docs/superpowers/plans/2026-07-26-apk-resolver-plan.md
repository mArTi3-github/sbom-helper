# APK Resolver Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an `ApkResolver` that returns `https://github.com/alpinelinux/aports/` for any PURL with type `apk`, placed last in the resolver chain and toggleable via Settings.

**Architecture:** A local-only resolver (no network calls) that checks `purl_utils.validate().type == "apk"`. Follows the exact same pattern as `EcosystemsResolver`/`LibrariesIoResolver` — new file in `resolver/`, conditional append in `factory.py`, toggle in `AppSettings`, card in Settings UI.

**Tech Stack:** Python 3.12+ (FastAPI, Pydantic v2), Vue 3 (Composition API, Pinia), TypeScript.

## Global Constraints

- Resolver must be last in chain (after LibrariesIo)
- No network calls — purely local type check
- Config key: `apk_resolver_enabled` (bool, default `True`)
- UI placement: card between Libraries.io and ecosyste.ms cards
- No API key — just a boolean toggle
- Follow existing naming: snake_case for Python settings, camelCase for JS

---

### Task 1: Backend — ApkResolver class

**Files:**
- Create: `src/purl_resolver/resolver/apk.py`
- Test: `tests/test_apk_resolver.py`

**Interfaces:**
- Consumes: `Resolution`, `Resolver` from `.interface`; `PurlValidationError`, `validate` from `..purl_utils`
- Produces: `ApkResolver` class with `name` property → `"apk"` and `async def resolve(purl: str) -> Resolution`

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from purl_resolver.resolver.apk import ApkResolver
from purl_resolver.resolver.interface import Resolution

pytestmark = pytest.mark.asyncio


async def test_resolve_apk_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/curl@7.83.0-r0")
    assert result.repository_url == "https://github.com/alpinelinux/aports/"
    assert result.purl == "pkg:apk/alpine/curl@7.83.0-r0"


async def test_resolve_apk_with_qualifiers():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:apk/alpine/apk@2.12.9-r3?arch=x86")
    assert result.repository_url == "https://github.com/alpinelinux/aports/"


async def test_resolve_non_apk_type():
    resolver = ApkResolver()
    result = await resolver.resolve("pkg:pypi/requests@2.31.0")
    assert result.repository_url is None
    assert any("Unsupported package type" in w for w in result.warnings)


async def test_resolve_invalid_purl():
    resolver = ApkResolver()
    result = await resolver.resolve("not-a-purl")
    assert result.repository_url is None
    assert any("Invalid PURL" in w for w in result.warnings)


def test_resolver_name():
    resolver = ApkResolver()
    assert resolver.name == "apk"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && source .venv/bin/activate && python -m pytest tests/test_apk_resolver.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Write minimal implementation**

```python
from __future__ import annotations

import logging

from ..purl_utils import PurlValidationError, validate
from .interface import Resolution, Resolver

logger = logging.getLogger(__name__)


class ApkResolver(Resolver):

    @property
    def name(self) -> str:
        return "apk"

    async def resolve(self, purl: str) -> Resolution:
        try:
            components = validate(purl)
        except PurlValidationError as e:
            return Resolution(purl=purl, warnings=[f"Invalid PURL: {e}"])

        if components.type != "apk":
            return Resolution(
                purl=purl,
                warnings=[f"Unsupported package type '{components.type}' for APK resolver"],
            )

        return Resolution(
            purl=purl,
            repository_url="https://github.com/alpinelinux/aports/",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && source .venv/bin/activate && python -m pytest tests/test_apk_resolver.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit (optional)**

```bash
git add src/purl_resolver/resolver/apk.py tests/test_apk_resolver.py
git commit -m "feat: add ApkResolver for Alpine Linux APK packages"
```

---

### Task 2: Backend — wire ApkResolver into factory + settings

**Files:**
- Modify: `src/purl_resolver/resolver/factory.py`
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `src/purl_resolver/routes/settings.py`

**Interfaces:**
- Consumes: `ApkResolver` from `.apk`
- Produces: `build_resolvers()` appends `ApkResolver` last when `app_settings.apk_resolver_enabled` is `True`; `AppSettings.apk_resolver_enabled` field; `SettingsUpdate` field; serialized in API responses

- [ ] **Step 1: Tests first — add test to existing settings store test**

Add to `tests/test_settings_store.py` (after `TestEcosystemsSettings` or similar):

```python
class TestApkSettings:
    def test_default_enabled(self):
        settings = AppSettings()
        assert settings.apk_resolver_enabled is True

    def test_save_and_load(self, tmp_path):
        store = SettingsStore(path=tmp_path / "settings.json")
        app_settings = AppSettings(apk_resolver_enabled=False)
        store.save(app_settings)
        loaded = store.load()
        assert loaded.apk_resolver_enabled is False
```

Also update `tests/test_factory.py` or create one to verify chain ordering. If no factory test exists, add a quick inline test in `test_apk_resolver.py`:

```python
async def test_apk_resolver_is_last_in_chain(monkeypatch):
    from purl_resolver.settings_store import AppSettings
    from purl_resolver.config import Settings
    from purl_resolver.resolver.factory import build_resolvers

    app_settings = AppSettings(
        ecosystems_enabled=False,
        librariesio_enabled=False,
        apk_resolver_enabled=True,
    )
    resolvers = build_resolvers(Settings(), app_settings)
    assert resolvers[-1].name == "apk"
```

- [ ] **Step 2: Run tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && source .venv/bin/activate && python -m pytest tests/test_apk_resolver.py tests/test_settings_store.py -v`
Expected: new tests fail

- [ ] **Step 3: Modify `settings_store.py` — add field**

In `AppSettings` (after existing resolver fields, e.g. after line 24):

```python
    apk_resolver_enabled: bool = True
```

- [ ] **Step 4: Modify `factory.py` — import and append**

Add import after line 7:
```python
from .apk import ApkResolver
```

Add after LibrariesIo block (after line 40):
```python
    if app_settings.apk_resolver_enabled:
        resolvers.append(ApkResolver())
```

- [ ] **Step 5: Modify `routes/settings.py` — SettingsUpdate model**

Add field to `SettingsUpdate` (after existing resolver fields, e.g. after line 39):
```python
    apk_resolver_enabled: bool | None = None
```

Add to GET response dict (after line 79, for example):
```python
        "apk_resolver_enabled": app_settings.apk_resolver_enabled,
```

Add to PATCH response dict (after line 135, for example):
```python
        "apk_resolver_enabled": updated.apk_resolver_enabled,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && source .venv/bin/activate && python -m pytest tests/test_apk_resolver.py tests/test_settings_store.py -v`
Expected: all PASS

- [ ] **Step 7: Commit (optional)**

```bash
git add src/purl_resolver/resolver/factory.py src/purl_resolver/settings_store.py src/purl_resolver/routes/settings.py
git commit -m "feat: wire ApkResolver into factory and settings"
```

---

### Task 3: Frontend — types, store, settings UI, translations

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/useSettingsStore.ts`
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/i18n/locales/en.json`
- Modify: `frontend/src/i18n/locales/ru.json`

**Interfaces:**
- Consumes: backend API returns `apk_resolver_enabled`
- Produces: toggle on Settings page that calls `PATCH /api/v1/settings` with `{ apk_resolver_enabled: bool }`

- [ ] **Step 1: Update `frontend/src/types/api.ts`**

Add to `SettingsResponse` interface:
```typescript
  apk_resolver_enabled: boolean
```

Add to `SettingsUpdate` interface:
```typescript
  apk_resolver_enabled?: boolean
```

- [ ] **Step 2: Update `frontend/src/stores/useSettingsStore.ts`**

Add ref:
```typescript
const apkEnabled = ref(false)
```

Add to load():
```typescript
apkEnabled.value = data.apk_resolver_enabled
```

Add to return block:
```typescript
    apkEnabled,
```

- [ ] **Step 3: Update `frontend/src/views/Settings.vue`**

Add to the destructured store refs (around line 319):
```typescript
  apkEnabled,
```

Add card after the Libraries.io card (after line 150) and before the ecosyste.ms card:

```html
      <div class="card">
        <div class="card-title">{{ t('settings.apkResolver.title') }}</div>
        <div class="setting-row">
          <div>
            <div class="setting-label">{{ t('settings.apkResolver.enable') }}</div>
            <div class="setting-desc">{{ t('settings.apkResolver.enableDesc') }}</div>
          </div>
          <label class="toggle">
            <input type="checkbox" v-model="apkEnabled" @change="debouncedAutoSave({ apk_resolver_enabled: apkEnabled })">
            <span class="toggle-slider"></span>
          </label>
        </div>
      </div>
```

- [ ] **Step 4: Update `frontend/src/i18n/locales/en.json`**

Add under `"settings"` key (between `"librariesio"` and `"ecosystems"` sections, around line 190):

```json
    "apkResolver": {
      "title": "APK Resolver (Alpine Linux)",
      "enable": "Enable APK resolver",
      "enableDesc": "When enabled, Alpine Linux APK packages (pkg:apk/...) resolve to https://github.com/alpinelinux/aports/ as a fallback."
    },
```

- [ ] **Step 5: Update `frontend/src/i18n/locales/ru.json`**

```json
    "apkResolver": {
      "title": "APK резолвер (Alpine Linux)",
      "enable": "Включить APK резолвер",
      "enableDesc": "При включении пакеты Alpine Linux APK (pkg:apk/...) резолвятся в https://github.com/alpinelinux/aports/ как запасной вариант."
    },
```

- [ ] **Step 6: Verify frontend builds**

Run: `cd /home/administrator/Desktop/projects/sbom-helper/frontend && npm run build`
Expected: No TypeScript or build errors

- [ ] **Step 7: Commit (optional)**

```bash
git add frontend/src/types/api.ts frontend/src/stores/useSettingsStore.ts frontend/src/views/Settings.vue frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json
git commit -m "feat: add APK resolver settings toggle in frontend"
```
