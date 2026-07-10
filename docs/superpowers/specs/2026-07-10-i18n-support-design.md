# i18n / Multilingual Support for sbom-helper

## Overview

Add full bilingual support (English + Russian) to the sbom-helper web UI. Users can switch between languages via the Settings page; the choice persists across sessions via localStorage + backend settings. API error messages are refactored from human-readable text to structured machine codes, with translation done on the frontend.

## Architecture

```
┌─────────────────────────────────────────────────┐
│                    Frontend (Vue 3)              │
│                                                   │
│  vue-i18n (Composition API)                       │
│  ├─ en.json ── all UI strings in English          │
│  └─ ru.json ── all UI strings in Russian          │
│                                                   │
│  Language detection:                               │
│  1. localStorage.getItem('locale')                 │
│  2. navigator.language.startsWith('ru') ? 'ru'     │
│  3. 'en' (fallback)                                │
│                                                   │
│  On language change:                               │
│  → i18n.global.locale.value = lang                │
│  → localStorage.setItem('locale', lang)            │
│  → PATCH /api/v1/settings { language: lang }      │
└──────────────────┬────────────────────────────────┘
                   │ HTTP JSON
                   ▼
┌─────────────────────────────────────────────────┐
│               Backend (FastAPI)                  │
│                                                   │
│  GET/PATCH /api/v1/settings                       │
│  └─ language: "en" | "ru" (new field)             │
│                                                   │
│  Error responses:                                  │
│  {"error": "file_too_large", "max_size_mb": 200}  │
│  {"error": "invalid_sbom", "detail": "..."}       │
│  ← machine-readable codes, frontend translates     │
└─────────────────────────────────────────────────┘
```

## Key Files

### New files
- `frontend/src/i18n/index.ts` — `createI18n()` config
- `frontend/src/i18n/locales/en.json` — English translations
- `frontend/src/i18n/locales/ru.json` — Russian translations

### Modified files
- `frontend/src/main.ts` — install i18n plugin, detect initial locale
- `frontend/vite.config.ts` — add `@intlify/unplugin-vue-i18n` plugin
- `frontend/src/stores/useSettingsStore.ts` — add `language` field
- `frontend/src/views/Settings.vue` — add language selector
- `frontend/src/App.vue` — replace hardcoded strings
- `frontend/src/components/AppNav.vue` — replace hardcoded route names
- `frontend/src/views/*.vue` (all 6 views) — replace hardcoded strings
- `frontend/src/components/FileUploadZone.vue` — replace hardcoded strings
- `frontend/src/components/ModalDialog.vue` — replace hardcoded strings
- `frontend/src/components/db/*.vue` — replace hardcoded strings
- `src/purl_resolver/settings_store.py` — add `language` to `AppSettings`
- `src/purl_resolver/routes/settings.py` — add `language` to `SettingsUpdate`
- `src/purl_resolver/routes/*.py` — refactor error responses

## Frontend Details

### vue-i18n Setup

```ts
// i18n/index.ts
import { createI18n } from 'vue-i18n'
import en from './locales/en.json'
import ru from './locales/ru.json'

export const i18n = createI18n({
  legacy: false,
  locale: 'en',
  fallbackLocale: 'en',
  messages: { en, ru }
})
```

```ts
// main.ts — before app.mount()
const saved = localStorage.getItem('locale')
const browser = navigator.language.startsWith('ru') ? 'ru' : 'en'
i18n.global.locale.value = saved ?? browser
app.use(i18n)
```

### Vite Config

```ts
// vite.config.ts
import VueI18nPlugin from '@intlify/unplugin-vue-i18n/vite'

export default defineConfig({
  plugins: [
    vue(),
    VueI18nPlugin({
      include: [path.resolve(__dirname, 'src/i18n/locales/**')]
    })
  ]
})
```

### Locale File Structure

Grouping by domain:

| Key | Content |
|-----|---------|
| `common` | Shared: save, cancel, close, download, upload, delete, edit, apply, reset, search, file, loading, error, noData, pageNotFound, goHome |
| `nav` | Route labels: purlResolver, sbomUpdater, imagesListConverter, dbAdmin, settings |
| `purlResolver` | PURL Resolver page strings |
| `sbomUpdater` | SBOM Updater page strings (currently Russian → moved to ru.json, English added to en.json) |
| `imagesListConverter` | Images List Converter page strings |
| `dbAdmin` | Database admin page + sub-component strings |
| `settings` | Settings page strings + language selector |
| `errors` | Error messages mapped from backend `error` codes |
| `status` | SBOM status labels: found, notFound, ignored, removed, skipped |

### Component Migration

Every `.vue` file gets:
```vue
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
const { t } = useI18n()
</script>
```

Template strings replaced:
- `{{ 'Some text' }}` → `{{ t('domain.key') }}`
- `:label="'Text'"` → `:label="t('domain.key')"`

Status labels from backend (`found`, `not_found`, etc.) mapped via:
```ts
t('status.' + statusKey.replace('-', '_'))
```

### Language Persistence

Two-layer approach:
1. **localStorage** — instant, works offline. Set on every language change.
2. **Backend settings** — survives cache clear, syncs across devices.

On page load:
1. Check `localStorage` → use it
2. If not set, detect browser locale → use it
3. If browser doesn't match ru, fallback to `'en'`
4. When `useSettingsStore.load()` resolves, if backend has `language` set, override locale + localStorage

### Language Switcher (Settings.vue)

```vue
<select :value="locale" @change="setLanguage">
  <option value="en">{{ t('settings.languageEn') }}</option>
  <option value="ru">{{ t('settings.languageRu') }}</option>
</select>
```

No URL prefix approach (no `/:locale/` routes) — overkill for this project.

## Backend Details

### AppSettings — new field

```python
# settings_store.py
from typing import Literal

class AppSettings(BaseModel):
    language: Literal['en', 'ru'] = 'en'
    # ... existing fields
```

### SettingsUpdate — new field

```python
# routes/settings.py
class SettingsUpdate(BaseModel):
    language: Literal['en', 'ru'] | None = None
    # ... existing fields
```

### Error Response Refactoring

**Pattern:** Responses with `{"error": "<code>", "message": "<human_text>"}` → remove `message`, add structured fields where needed. For technical debugging details (e.g., SbomParseError context), an optional `detail` field may remain — shown in UI as expandable technical info, not translated.

| Endpoint | Current | New |
|----------|---------|-----|
| `POST /api/v1/resolve` | `{"error":"file_too_large","message":"..."}` | `{"error":"file_too_large","max_size_mb":200}` |
| `POST /api/v1/resolve` | `{"error":"network_unavailable","message":"..."}` | `{"error":"network_unavailable"}` |
| `POST /api/v1/resolve` | `{"error":"invalid_json","message":"..."}` | `{"error":"invalid_json"}` |
| `POST /api/v1/resolve` | `{"error":"invalid_sbom","message":"..."}` | `{"error":"invalid_sbom"}` + optional `detail` with parse error |
| `POST /api/v1/resolve` | `{"error":"invalid_purl","message":"..."}` | `{"error":"invalid_purl"}` |
| `POST /api/v1/resolve` | `{"error":"upstream_error","message":"..."}` | `{"error":"upstream_error"}` |
| `PATCH /api/v1/settings` | `{"error":"invalid_token","message":"..."}` | `{"error":"invalid_token"}` |
| `POST /api/v1/settings/check-github-token` | `{"error":"token_not_set","message":"..."}` | `{"error":"token_not_set"}` |
| `POST /api/v1/convert/images-list` | `{"error":"file_too_large","message":"..."}` | `{"error":"file_too_large","max_size_mb":200}` |
| `POST /api/v1/convert/images-list` | `{"error":"invalid_json","message":"..."}` | `{"error":"invalid_json"}` |
| `POST /api/v1/convert/images-list` | `{"error":"invalid_sbom","message":"..."}` | `{"error":"invalid_sbom"}` + optional `detail` with parse error |
| `PATCH /api/v1/db/purls` | `{"error":"not_found","message":"PURL not found"}` | `{"error":"purl_not_found"}` |
| `PATCH /api/v1/db/purls` | `{"error":"invalid_update","message":"..."}` | `{"error":"invalid_update"}` |
| `POST /api/v1/db/import` | `{"error":"invalid_csv","message":"..."}` | `{"error":"invalid_csv"}` |
| `GET /api/v1/settings` | `{"status":"ok"}` | no change (not user-facing) |
| `GET /health` | `{"status":"ok"}` | no change (not user-facing) |

**NOT refactored:** resolver warnings (stay English), SBOM report `status` fields (already codes), `found_by` field (already codes), `warnings` arrays (technical/debug messages).

### Frontend API client changes

The `apiFetch` wrapper and individual client methods need to handle responses:
- On error (non-2xx), if body has `error` code → frontend translates via `t('errors.' + errorCode, data)`
- Remove any client-side parsing of the `message` field

## Migration Order

1. **Infrastructure setup:** install vue-i18n, configure Vite plugin, create i18n/index.ts, en.json, ru.json
2. **Settings:** add language to backend AppSettings + SettingsUpdate + route; add language to frontend store; add language switcher to Settings.vue
3. **Simple components:** NotFound.vue, App.vue, AppNav.vue, ModalDialog.vue
4. **English-only views:** PurlResolver.vue, Settings.vue (existing strings), DatabaseAdmin.vue + sub-components
5. **Mixed RU/EN components:** FileUploadZone.vue
6. **Mostly-Russian views:** SbomUpdater.vue, ImagesListConverter.vue
7. **Backend error response refactoring:** all route handlers
8. **Frontend error handling:** update apiFetch/api client to use translated error codes
9. **Verification:** toggle language, ensure all strings display correctly in both locales

## Invariants

- No hardcoded user-facing strings remain in any `.vue` file
- `en.json` and `ru.json` share identical key structure (same keys, different values)
- Backend never returns user-facing human-readable text in error responses
- Language choice survives page refresh (localStorage) and server restart (backend settings)
- API error responses always include `error` field (machine code)
- `@intlify/unplugin-vue-i18n` compiles messages at build time
