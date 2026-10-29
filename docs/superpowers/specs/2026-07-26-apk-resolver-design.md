# APK Resolver — Design

## Problem

Alpine Linux APK packages (`pkg:apk/…`) are not handled by any existing resolver. When purl2repo, ecosyste.ms, and libraries.io all fail to find a repository URL for an APK package, there is no fallback that provides a meaningful source-code reference.

## Solution

Add an `ApkResolver` as the **last** resolver in the chain. For any PURL with type `apk`, it returns the constant URL `https://github.com/alpinelinux/aports/` — the canonical repository containing Alpine package build scripts and patches.

## Decisions

1. **Constant URL**: Always returns `https://github.com/alpinelinux/aports/`. Alpine packages are built from upstream source with patches from aports; the aports repo is the authoritative reference.
2. **Last in chain**: Added after LibrariesIoResolver. Only reached when all prior resolvers (purl2repo, ecosyste.ms, libraries.io) returned no URL.
3. **Enabled by default**: `apk_resolver_enabled: bool = True`. The resolver is purely local (no network calls), so there is no cost to having it enabled.
4. **Toggleable**: Disabled via Settings page toggle, same pattern as ecosyste.ms / libraries.io.
5. **No API key**: No external service, no authentication needed.
6. **Graceful degradation**: For non-apk PURLs, returns a warning Resolution with no URL, allowing the chain to continue.

## Architecture

### New file: `src/purl_resolver/resolver/apk.py`

```python
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

### Modified: `src/purl_resolver/resolver/factory.py`

Add `ApkResolver` import and append it after LibrariesIo:

```python
if app_settings.apk_resolver_enabled:
    resolvers.append(ApkResolver())
```

### Modified: `src/purl_resolver/settings_store.py`

Add field to `AppSettings`:

```python
apk_resolver_enabled: bool = True
```

### Modified: `src/purl_resolver/routes/settings.py`

- Add `apk_resolver_enabled: bool | None = None` to `SettingsUpdate`
- Serialize `apk_resolver_enabled` in GET and PATCH responses

### Modified: `frontend/src/types/api.ts`

- Add `apk_resolver_enabled: boolean` to `SettingsResponse`
- Add `apk_resolver_enabled?: boolean` to `SettingsUpdate`

### Modified: `frontend/src/stores/useSettingsStore.ts`

- Add `const apkEnabled = ref(false)`
- Load from API response in `load()`

### Modified: `frontend/src/views/Settings.vue`

New card after Libraries.io card (before ecosyste.ms):

```html
<div class="card">
  <div class="card-title">{{ t('settings.apkResolver.title') }}</div>
  <div class="setting-row">
    <div>
      <div class="setting-label">{{ t('settings.apkResolver.enable') }}</div>
      <div class="setting-desc">{{ t('settings.apkResolver.enableDesc') }}</div>
    </div>
    <label class="toggle">
      <input type="checkbox" v-model="apkEnabled"
             @change="debouncedAutoSave({ apk_resolver_enabled: apkEnabled })">
      <span class="toggle-slider"></span>
    </label>
  </div>
</div>
```

### Modified: `frontend/src/i18n/locales/en.json` and `ru.json`

```json
"apkResolver": {
  "title": "APK Resolver (Alpine Linux)",
  "enable": "Enable APK resolver",
  "enableDesc": "When enabled, Alpine Linux APK packages (pkg:apk/...) resolve to https://github.com/alpinelinux/aports/ as a fallback."
}
```

Russian translation:

```json
"apkResolver": {
  "title": "APK резолвер (Alpine Linux)",
  "enable": "Включить APK резолвер",
  "enableDesc": "При включении пакеты Alpine Linux APK (pkg:apk/...) резолвятся в https://github.com/alpinelinux/aports/ как запасной вариант."
}
```

### New file: `tests/test_apk_resolver.py`

| Test | Expectation |
|---|---|
| `pkg:apk/alpine/curl@7.83.0-r0` | returns `repository_url = "https://github.com/alpinelinux/aports/"` |
| `pkg:apk/alpine/apk@2.12.9-r3?arch=x86` | returns the same URL (qualifiers ignored) |
| `pkg:pypi/requests` | returns warning for unsupported type |
| `not-a-purl` | returns warning for invalid PURL |
| `.name` property | returns `"apk"` |

## Data Flow

```
PURL → Purl2RepoResolver → (EcosystemsResolver) → (LibrariesIoResolver) → ApkResolver
                                                              ↑               ↑
                                                     network fallbacks    local fallback
                                                                     (constant URL)
```

## Files Changed

| File | Change |
|---|---|
| `src/purl_resolver/resolver/apk.py` | **New** |
| `src/purl_resolver/resolver/__init__.py` | Empty, no change needed |
| `src/purl_resolver/resolver/factory.py` | Add ApkResolver import and conditional append |
| `src/purl_resolver/settings_store.py` | Add `apk_resolver_enabled` field |
| `src/purl_resolver/routes/settings.py` | Add field to update model and response |
| `frontend/src/types/api.ts` | Add `apk_resolver_enabled` to response/update |
| `frontend/src/stores/useSettingsStore.ts` | Add ref, load from API |
| `frontend/src/views/Settings.vue` | Add card with toggle |
| `frontend/src/i18n/locales/en.json` | Add translations |
| `frontend/src/i18n/locales/ru.json` | Add translations |
| `tests/test_apk_resolver.py` | **New** |
