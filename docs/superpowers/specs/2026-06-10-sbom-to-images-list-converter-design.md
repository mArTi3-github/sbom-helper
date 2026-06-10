# SBOM-to-images-list Converter Design

## Problem Statement

Необходимо добавить новый инструмент "SBOM-to-images-list Converter", который на основе переданного CycloneDX SBOM-файла формирует машиночитаемый список docker-образов продукта в формате CycloneDX SBOM в соответствии с требованиями `images_list_description_fstec.md`.

Инструмент должен:
1. Принимать на вход CycloneDX SBOM-файл
2. Проверять, является ли он уже корректным списком образов (все top-level components имеют `type=container`)
3. Если нет — преобразовывать: собрать все `type=container` компоненты со всех уровней вложенности, переместить их на верхний уровень, удалить non-container компоненты
4. Возвращать результат вместе с мета-информацией о преобразовании и таблицей образов с флагами недостающих полей

## Architecture

### Layer Placement

```
HTTP Client (Browser)
    |
    | POST /api/v1/convert/images-list (multipart)
    v
API Layer (routes/images_list.py)
    |
    v
SBOM Module (sbom/images_list_converter.py)
    |
    v
CycloneDXParser (sbom/parser.py) — формат validation
```

Новый модуль `ImagesListConverter` добавляется в существующий пакет `sbom/`. Он переиспользует `CycloneDXParser` для валидации формата SBOM.

### Files

| File | Change |
|---|---|
| `src/purl_resolver/sbom/images_list_converter.py` | **NEW** — Core conversion logic |
| `src/purl_resolver/routes/images_list.py` | **NEW** — API endpoint |
| `src/purl_resolver/templates/images-list-converter.html` | **NEW** — Web UI page |
| `src/purl_resolver/router.py` | **EDIT** — Add new routes and template handler |
| `tests/test_images_list_converter.py` | **NEW** — Unit + API tests |

## Core Module: `images_list_converter.py`

### Data Structures

```python
@dataclass
class ImageInfo:
    name: str | None
    version: str | None
    missing_components: bool   # True если нет собственного непустого components
    missing_name: bool         # True если name пустое/отсутствует
    missing_version: bool      # True если version пустое/отсутствует
    missing_properties: bool   # True если properties пустое/отсутствует

@dataclass
class ImagesListConversionResult:
    images_list: dict
    was_transformed: bool
    images: list[ImageInfo]
```

### Algorithm

1. **Validate:** `CycloneDXParser.parse(sbom_data)` — проверяет `bomFormat: CycloneDX`
2. **Check needs transform:** проверить все элементы `components` верхнего уровня — если все имеют `type=container`, то `needs_transform=False`; иначе `True`
3. **If not needs_transform:**
   - Собрать `ImageInfo` для существующих top-level container-компонентов
   - `was_transformed=False`, `images_list = исходный sbom_data`
4. **If needs_transform:**
   - Рекурсивно обойти весь документ, собрать ВСЕ компоненты с `type=container` (включая вложенные)
   - Установить собранные контейнеры как новый `components` верхнего уровня
   - Удалить из `components` верхнего уровня любые элементы с `type != "container"`
   - Остальные поля корня (`bomFormat`, `specVersion`, `version`, `metadata` и т.д.) не трогать
   - Собрать `ImageInfo` для каждого контейнера в итоговом списке
   - `was_transformed=True`
5. **Build result:** `ImagesListConversionResult(images_list, was_transformed, images)`

### Key Behavior

- Компоненты `type=container` со всех уровней вложенности становятся top-level
- Если контейнер сам имеет вложенные `components` — они сохраняются (как его подкомпоненты)
- Если во входном SBOM нет ни одного `type=container` — результат будет иметь пустой `components`
- Поле `version` корневого объекта не инкрементируется (в отличие от SBOM enrichment)

## API Contract

### `POST /api/v1/convert/images-list`

**Request:** `multipart/form-data` with field `file` containing a CycloneDX JSON file.
- Maximum file size: 200 MB (configurable via `SBOM_MAX_FILE_SIZE`)
- File must be valid JSON with `bomFormat: "CycloneDX"`

**Success Response (200):**
```json
{
  "was_transformed": true,
  "images": [
    {
      "name": "manager",
      "version": "3.0.0",
      "missing_components": false,
      "missing_name": false,
      "missing_version": false,
      "missing_properties": false
    },
    {
      "name": "gateway",
      "version": "2.31.0",
      "missing_components": false,
      "missing_name": false,
      "missing_version": false,
      "missing_properties": true
    }
  ],
  "images_list": { "bomFormat": "CycloneDX"}
}
```

**Error Response (400) — invalid JSON:**
```json
{
  "error": "invalid_json",
  "message": "Invalid JSON: Expecting value: line 1 column 1"
}
```

**Error Response (400) — invalid SBOM format:**
```json
{
  "error": "invalid_sbom",
  "message": "Missing required field: bomFormat"
}
```

**Error Response (413) — file too large:**
```json
{
  "error": "file_too_large",
  "message": "File size exceeds maximum of 200 MB"
}
```

**Validation Error (422) — missing file field:**
Standard FastAPI/Pydantic 422 response.

## Web UI: `images-list-converter.html`

### Layout

- **Navigation bar** — существующий навбар + новая ссылка "Images List Converter"
- **Upload area** — drag-and-drop для .json файлов (аналогично `sbom.html`)
- **Convert button** — "Конвертировать", disabled пока не выбран файл
- **Loading spinner** — во время обработки
- **Results section:**
  - Карточка статуса: "Преобразований не требуется" (зеленый) / "Выполнено преобразование" (желтый)
  - Таблица образов со столбцами:
    - Имя образа (`name`)
    - Версия (`version`)
    - `Отсутствуют компоненты` — отметка только если проблема есть
    - `Не заполнено поле name` — отметка только если проблема есть
    - `Не заполнено поле version` — отметка только если проблема есть
    - `Не заполнено поле properties` — отметка только если проблема есть
  - Кнопка "Скачать список образов" — скачивает итоговый JSON

### Page Route

```python
@router.get("/images-list-converter", response_class=HTMLResponse)
async def images_list_converter_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="images-list-converter.html")
```

### JavaScript Behavior

- Single-page behavior via `fetch()` (никаких перезагрузок)
- Submit button disabled while request is in flight
- Drag-and-drop поддерживается (как в sbom.html)
- Таблица флагов: отметка ставится **только** когда условие выполняется; если всё в порядке — ячейка пуста

## Error Handling

| Condition | HTTP Status | Error Code |
|---|---|---|
| Invalid JSON | 400 | `invalid_json` |
| Invalid SBOM format (missing bomFormat) | 400 | `invalid_sbom` |
| File too large | 413 | `file_too_large` |
| Missing file field | 422 | (Pydantic validation) |

## Testing Strategy

### Unit Tests (`test_images_list_converter.py`)

| Test Case | Expected Result |
|---|---|
| SBOM already valid images list (all top-level `type=container`) | `was_transformed=False`, images list unchanged |
| SBOM with `type=application` top-level + `type=container` nested | `was_transformed=True`, containers promoted to top-level |
| SBOM with no containers at all | Empty `components` in result |
| Container missing `name` | `missing_name=True` for that image |
| Container missing `version` | `missing_version=True` for that image |
| Container missing `properties` | `missing_properties=True` for that image |
| Container with no nested `components` | `missing_components=True` for that image |
| Invalid JSON input | `SbomParseError` raised |
| Non-CycloneDX JSON | `SbomParseError` raised |

### API Tests (via TestClient)

| Test Case | Expected Result |
|---|---|
| POST without file | 422 |
| POST with valid SBOM | 200, correct response shape |
| POST with invalid JSON | 400 with error code `invalid_json` |
| POST with non-SBOM JSON | 400 with error code `invalid_sbom` |

## Dependencies

- Existing `CycloneDXParser` from `sbom/parser.py` — only validates `bomFormat: CycloneDX`, specVersion is NOT checked
- Existing `SbomParseError` from `sbom/parser.py`
- Existing file size limit config (`SBOM_MAX_FILE_SIZE`)
- No new external dependencies