# JSON Indent Setting — Design Spec

## Problem

При скачивании обогащённого SBOM (SBOM Updater) или списка docker-образов (Images List Converter)
JSON форматируется с жёстко заданным отступом в 2 пробела (`frontend/src/composables/useDownload.ts:2`).
Пользователь не может выбрать удобный для себя размер отступа.

## Solution

Добавить настройку `json_indent` в существующую систему настроек (бэкенд `AppSettings` + Pinia store на фронтенде)
и передавать её как параметр в `downloadJson()`.

## Изменения

### 1. Бэкенд — `src/purl_resolver/settings_store.py`

Добавить в `AppSettings`:

```python
json_indent: int = Field(default=4, ge=1, le=4)
```

### 2. Бэкенд — `src/purl_resolver/routes/settings.py`

Добавить в `SettingsUpdate`:

```python
json_indent: int | None = Field(None, ge=1, le=4)
```

Включить `json_indent` в словари, возвращаемые `GET /api/v1/settings` и `PATCH /api/v1/settings`.

### 3. Фронтенд — `frontend/src/types/api.ts`

Добавить:
- `json_indent: number` — в `SettingsResponse`
- `json_indent?: number` — в `SettingsUpdate`

### 4. Фронтенд — `frontend/src/stores/useSettingsStore.ts`

- Добавить `const jsonIndent = ref(4)`
- В `load()`: `jsonIndent.value = data.json_indent`
- Добавить `jsonIndent` в `return`

### 5. Фронтенд — `frontend/src/composables/useDownload.ts`

Изменить сигнатуру:

```ts
export function downloadJson(data: unknown, filename: string, indent: number = 4): void
```

Заменить `JSON.stringify(data, null, 2)` на `JSON.stringify(data, null, indent)`.

### 6. Фронтенд — `frontend/src/views/SbomUpdater.vue`

- Импортировать `useSettingsStore`
- В `downloadResult()`: получить `store.jsonIndent`, передать третьим аргументом в `downloadJson`

### 7. Фронтенд — `frontend/src/views/ImagesListConverter.vue`

Аналогично SbomUpdater.vue.

### 8. Фронтенд — `frontend/src/views/Settings.vue`

Добавить карточку "JSON Format" с `<select>` (значения 1, 2, 4), идентично существующему select для `log_level`.

## Границы изменений

- Не затрагивается API endpoint'ов `/api/v1/resolve/sbom` и `/api/v1/convert/images-list`
- Не затрагиваются тесты (настройка опциональна и не влияет на логику обработки)
- Не добавляется новых API-роутов