# Images List Deduplication Design

## Problem Statement

В машиночитаемом списке docker-образов, формируемом инструментом "Images List Converter", в список `components` попадают все найденные элементы с `type=container` без какой-либо дедупликации. Если в исходном SBOM один и тот же образ (одинаковый `purl`) встречается multiple раз на разных уровнях вложенности, в результирующем списке появляются дублирующиеся компоненты.

Необходимо:
1. Дедуплицировать компоненты в формируемом списке `components` по полю `purl`
2. В веб-интерфейсе добавить колонку "Удалено дублей", показывающую для каждого образа количество удалённых дублей

## Scope

Изменения затрагивают только модуль `ImagesListConverter` и его API/Frontend представление. Архитектура слоёв, формат CycloneDX 1.6 и остальные инструменты не меняются.

## Design

### Layer Placement

```
HTTP Client (Browser)
    |
    | POST /api/v1/convert/images-list
    v
API Layer (routes/images_list.py)
    |
    v
SBOM Module (sbom/images_list_converter.py)
    |  — _deduplicate_containers() NEW
    |  — _build_image_infos() modified
    v
CycloneDXParser (sbom/parser.py) — без изменений
```

### Key Decisions

1. **Дедупликация всегда активна** — выполняется независимо от `was_transformed`. Даже если входной SBOM уже является корректным списком образов (все top-level components имеют `type=container`), дубли всё равно удаляются.
2. **Ключ дедупликации — `purl`** — если у двух компонентов совпадает строковое значение поля `purl`, они считаются идентичными. Остальные поля не проверяются.
3. **Компоненты без `purl` не дедуплицируются** — если у компонента нет поля `purl` или его значение не является строкой, он считается уникальным.
4. **Семантика first-wins** — при обнаружении дубля сохраняется первый встреченный компонент, последующие отбрасываются.
5. **`was_transformed` обновляется при дедупликации** — флаг устанавливается в `True` если:
   - Были non-container top-level компоненты (потребовалось промотирование), ИЛИ
   - Был удалён хотя бы один дубль (данные были изменены)
   
   Если входной SBOM уже является корректным списком образов И дублей не найдено — `was_transformed = False`.

### Backend Changes

#### `images_list_converter.py`

**Новое поле `ImageInfo.duplicates_removed`**:
```python
@dataclass
class ImageInfo:
    name: str | None
    version: str | None
    missing_components: bool = False
    missing_name: bool = False
    missing_version: bool = False
    missing_properties: bool = False
    duplicates_removed: int = 0  # NEW
```

**Новый метод `_deduplicate_containers`**:
- Принимает `list[dict]` (список container-компонентов)
- Возвращает кортеж `(deduped: list[dict], dup_counts: dict[str, int])`
- `dup_counts` мапит `purl → количество удалённых дублей` только для purl, которые остались в финальном списке

```python
@classmethod
def _deduplicate_containers(cls, containers: list[dict]) -> tuple[list[dict], dict[str, int]]:
    seen: set[str] = set()
    dup_counts: dict[str, int] = {}
    deduped: list[dict] = []
    for comp in containers:
        purl = comp.get("purl")
        if isinstance(purl, str):
            if purl in seen:
                dup_counts[purl] = dup_counts.get(purl, 0) + 1
                continue
            seen.add(purl)
        deduped.append(comp)
    return deduped, dup_counts
```

**Изменение `_build_image_infos`** — принимает опциональный `dup_counts`:
```python
@classmethod
def _build_image_infos(cls, components: list[dict], dup_counts: dict[str, int] | None = None) -> list[ImageInfo]:
    if dup_counts is None:
        dup_counts = {}
    for comp in components:
        ...
        purl = comp.get("purl")
        dr = dup_counts.get(purl, 0) if isinstance(purl, str) else 0
        info = ImageInfo(..., duplicates_removed=dr)
```

**Изменение `convert()`** — оба пути проходят через `_deduplicate_containers`:
```python
@classmethod
def convert(cls, sbom_data: object) -> ImagesListConversionResult:
    data = cls._validate(sbom_data)
    top_components = data.get("components", [])

    if cls._all_are_containers(top_components):
        containers = top_components
        was_transformed = False
    else:
        containers = cls._collect_containers(data)
        was_transformed = True

    deduped, dup_counts = cls._deduplicate_containers(containers)

    # If any duplicates were removed, data was transformed
    if dup_counts:
        was_transformed = True

    images = cls._build_image_infos(deduped, dup_counts)
    result_sbom = dict(data)
    result_sbom["components"] = deduped

    return ImagesListConversionResult(
        images_list=result_sbom, was_transformed=was_transformed, images=images
    )
```

#### `routes/images_list.py`

В каждую запись массива `images` добавляется поле `duplicates_removed`:
```python
"images": [
    {
        "name": img.name,
        "version": img.version,
        "missing_components": img.missing_components,
        "missing_name": img.missing_name,
        "missing_version": img.missing_version,
        "missing_properties": img.missing_properties,
        "duplicates_removed": img.duplicates_removed,  # NEW
    }
    for img in result.images
],
```

### Frontend Changes

#### `types/api.ts`

```typescript
export interface ImageItem {
  name: string | null
  version: string | null
  missing_components: boolean
  missing_name: boolean
  missing_version: boolean
  missing_properties: boolean
  duplicates_removed: number  // NEW
}
```

#### `views/ImagesListConverter.vue`

В шаблоне таблицы добавляется колонка "Удалено дублей":

```html
<thead>
  <tr>
    <th>Имя образа</th>
    <th>Версия</th>
    <th>Заполнены компоненты</th>
    <th>Заполнено поле name</th>
    <th>Заполнено поле Properties</th>
    <th>Удалено дублей</th>  <!-- NEW -->
  </tr>
</thead>
<tbody>
  <tr v-for="(img, i) in result.images" :key="i">
    ...
    <td>{{ img.duplicates_removed > 0 ? img.duplicates_removed : '—' }}</td>
  </tr>
</tbody>
```

### Testing

#### Unit tests (`test_images_list_converter.py`)

1. **test_dedup_by_purl** — SBOM с тремя container-компонентами: два с одинаковым `purl`, один уникальный. Проверка: в `images_list["components"]` остается 2 элемента, `duplicates_removed` у первого = 1, у второго = 0.
2. **test_dedup_no_purl_not_deduped** — два контейнера без `purl` — оба остаются, `duplicates_removed = 0` у обоих.
3. **test_dedup_already_valid_list** — уже валидный список (все top-level containers) с дублями — проверка дедупликации.
4. **test_dedup_empty_list** — список без дублей — `deduped == original`, `dup_counts` пуст.
5. **test_dedup_multiple_purls** — несколько разных purl с разным количеством дублей — проверка `duplicates_removed` для каждого.

#### API test (`test_images_list_converter.py`)

6. **Расширение test_convert_response_shape** — проверка наличия поля `duplicates_removed` в каждом image объекта ответа.

## Data Flow Summary

```
Вход: CycloneDX SBOM JSON
  → CycloneDXParser.parse() — валидация формата
  → _all_are_containers() — проверка, нужна ли трансформация
  → Если да: _collect_containers() — рекурсивный сбор всех type=container
  → Если нет: top_components используются напрямую
  → _deduplicate_containers() — удаление дублей по purl, подсчёт удалённых
  → Формирование result_sbom с deduped components
  → _build_image_infos() — построение ImageInfo[] с duplicates_removed
  → API JSON response с was_transformed, images[], images_list
```

## Not In Scope

- Изменение формата CycloneDX — не требуется
- Изменение статус-карточки в UI — изменение следует автоматически из обновлённой логики `was_transformed`
- Дедупликация по другим полям (name/version) — только purl
