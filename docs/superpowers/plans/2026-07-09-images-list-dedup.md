# Images List Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate container components by `purl` in the Images List Converter output and show the removed count per image in the UI.

**Architecture:** Add `_deduplicate_containers` method to `ImagesListConverter` that deduplicates by `purl` (first-wins), returns deduped list + per-purl duplicate counts. Modify `ImageInfo` to carry `duplicates_removed`. Update `convert()` to always deduplicate and set `was_transformed=True` when any duplicate is removed. Pass the count through the API to the frontend table.

**Tech Stack:** Python 3.12, FastAPI, Vue 3 + TypeScript, pytest, Vitest

**Spec:** `docs/superpowers/specs/2026-07-09-images-list-dedup-design.md`

## Global Constraints

- Run all python commands inside `.venv` virtual environment (`source .venv/bin/activate`)
- All python tests with pytest: `python -m pytest tests/test_images_list_converter.py -v`
- Deduplication key is `purl` field; components without `purl` are treated as unique
- `was_transformed` is `True` if promotion occurred OR at least one duplicate was removed

---

## File Structure

| File | Change |
|------|--------|
| `src/purl_resolver/sbom/images_list_converter.py` | New `_deduplicate_containers()`, modified `ImageInfo`, `_build_image_infos()`, `convert()` |
| `src/purl_resolver/routes/images_list.py` | Add `duplicates_removed` to each image in API response |
| `frontend/src/types/api.ts` | Add `duplicates_removed: number` to `ImageItem` |
| `frontend/src/views/ImagesListConverter.vue` | Add column "Удалено дублей" |
| `tests/test_images_list_converter.py` | 5 new unit tests + 1 API test update |

---

### Task 1: Backend dedup logic + unit tests

**Files:**
- Modify: `src/purl_resolver/sbom/images_list_converter.py`
- Test: `tests/test_images_list_converter.py`

**Interfaces:**
- Consumes: existing `_collect_containers()`, `_walk_and_collect()`, `_all_are_containers()`
- Produces: `_deduplicate_containers(containers: list[dict]) -> tuple[list[dict], dict[str, int]]`; updated `ImageInfo.duplicates_removed: int`; updated `_build_image_infos(components, dup_counts?) -> list[ImageInfo]`; updated `convert()` logic

- [ ] **Step 1: Write the dedup unit tests (5 new tests)**

Add these test methods to `TestImagesListConverter` class in `tests/test_images_list_converter.py`:

```python
def test_dedup_by_purl(self) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "container",
                "name": "nginx",
                "version": "1.21",
                "purl": "pkg:docker/nginx@1.21",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "nginx",
                "version": "1.21",
                "purl": "pkg:docker/nginx@1.21",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "postgres",
                "version": "14",
                "purl": "pkg:docker/postgres@14",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
        ],
    }
    result = ImagesListConverter.convert(sbom)
    assert len(result.images_list["components"]) == 2
    assert result.images[0].name == "nginx"
    assert result.images[0].duplicates_removed == 1
    assert result.images[1].name == "postgres"
    assert result.images[1].duplicates_removed == 0

def test_dedup_no_purl_not_deduped(self) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "container",
                "name": "web",
                "version": "1.0",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "web",
                "version": "1.0",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
        ],
    }
    result = ImagesListConverter.convert(sbom)
    assert len(result.images_list["components"]) == 2
    assert result.images[0].duplicates_removed == 0
    assert result.images[1].duplicates_removed == 0

def test_dedup_already_valid_list_with_dups(self) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "container",
                "name": "nginx",
                "version": "1.21",
                "purl": "pkg:docker/nginx@1.21",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "nginx",
                "version": "1.21",
                "purl": "pkg:docker/nginx@1.21",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
        ],
    }
    result = ImagesListConverter.convert(sbom)
    assert result.was_transformed is True
    assert len(result.images_list["components"]) == 1
    assert result.images[0].duplicates_removed == 1

def test_dedup_no_duplicates(self) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "container",
                "name": "web",
                "version": "1.0",
                "purl": "pkg:docker/web@1.0",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
        ],
    }
    result = ImagesListConverter.convert(sbom)
    assert result.was_transformed is False
    assert len(result.images_list["components"]) == 1
    assert result.images[0].duplicates_removed == 0

def test_dedup_multiple_purls(self) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {
                "type": "container",
                "name": "a",
                "version": "1",
                "purl": "pkg:docker/a",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "a",
                "version": "1",
                "purl": "pkg:docker/a",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "b",
                "version": "1",
                "purl": "pkg:docker/b",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "b",
                "version": "1",
                "purl": "pkg:docker/b",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "b",
                "version": "1",
                "purl": "pkg:docker/b",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
            {
                "type": "container",
                "name": "c",
                "version": "1",
                "purl": "pkg:docker/c",
                "properties": [{"name": "GOST:attack_surface", "value": "no"}],
            },
        ],
    }
    result = ImagesListConverter.convert(sbom)
    assert len(result.images_list["components"]) == 3
    assert result.images[0].duplicates_removed == 1
    assert result.images[1].duplicates_removed == 2
    assert result.images[2].duplicates_removed == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_images_list_converter.py -v`
Expected: 5 new tests FAIL with `AttributeError` or `TypeError` (field `duplicates_removed` doesn't exist yet)

- [ ] **Step 3: Add `duplicates_removed` field to `ImageInfo`**

In `src/purl_resolver/sbom/images_list_converter.py`:

```python
@dataclass
class ImageInfo:
    name: str | None
    version: str | None
    missing_components: bool = False
    missing_name: bool = False
    missing_version: bool = False
    missing_properties: bool = False
    duplicates_removed: int = 0
```

- [ ] **Step 4: Implement `_deduplicate_containers` method**

In `src/purl_resolver/sbom/images_list_converter.py`, after `_collect_containers`:

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

- [ ] **Step 5: Update `_build_image_infos` to accept and use `dup_counts`**

Replace the existing method:

```python
@classmethod
def _build_image_infos(cls, components: list[dict], dup_counts: dict[str, int] | None = None) -> list[ImageInfo]:
    if dup_counts is None:
        dup_counts = {}
    images: list[ImageInfo] = []
    for comp in components:
        name = comp.get("name")
        version = comp.get("version")
        purl = comp.get("purl")
        dr = dup_counts.get(purl, 0) if isinstance(purl, str) else 0
        info = ImageInfo(
            name=name if isinstance(name, str) and name else None,
            version=version if isinstance(version, str) and version else None,
            missing_name=not (isinstance(name, str) and name),
            missing_version=not (isinstance(version, str) and version),
            missing_components=not cls._has_subcomponents(comp),
            missing_properties=not cls._has_properties(comp),
            duplicates_removed=dr,
        )
        images.append(info)
    return images
```

- [ ] **Step 6: Update `convert()` method**

Replace the existing method:

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

    if dup_counts:
        was_transformed = True

    images = cls._build_image_infos(deduped, dup_counts)
    result_sbom = dict(data)
    result_sbom["components"] = deduped

    return ImagesListConversionResult(
        images_list=result_sbom, was_transformed=was_transformed, images=images
    )
```

- [ ] **Step 7: Run all tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_images_list_converter.py -v`
Expected: 19 tests PASS (14 existing + 5 new)

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/sbom/images_list_converter.py tests/test_images_list_converter.py
git commit -m "feat: deduplicate container components by purl in images list converter"
```

---

### Task 2: API route update

**Files:**
- Modify: `src/purl_resolver/routes/images_list.py`
- Test: `tests/test_images_list_converter.py` (API test class)

**Interfaces:**
- Consumes: `ImageInfo.duplicates_removed` from Task 1
- Produces: `duplicates_removed: int` field in each image of the API JSON response

- [ ] **Step 1: Update API response shape test**

In `TestImagesListConverterAPI.test_convert_response_shape`, add assertions inside the `if data["images"]:` block:

```python
assert "duplicates_removed" in img
assert isinstance(img["duplicates_removed"], int)
```

- [ ] **Step 2: Run API test to verify it fails**

Run: `source .venv/bin/activate && python -m pytest tests/test_images_list_converter.py::TestImagesListConverterAPI -v`
Expected: `test_convert_response_shape` FAILS (field `duplicates_removed` not in response)

- [ ] **Step 3: Add `duplicates_removed` to route response**

In `src/purl_resolver/routes/images_list.py`, add the field to each image dict:

```python
"images": [
    {
        "name": img.name,
        "version": img.version,
        "missing_components": img.missing_components,
        "missing_name": img.missing_name,
        "missing_version": img.missing_version,
        "missing_properties": img.missing_properties,
        "duplicates_removed": img.duplicates_removed,
    }
    for img in result.images
],
```

- [ ] **Step 4: Run API tests to verify they pass**

Run: `source .venv/bin/activate && python -m pytest tests/test_images_list_converter.py::TestImagesListConverterAPI -v`
Expected: 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/images_list.py tests/test_images_list_converter.py
git commit -m "feat: add duplicates_removed field to images list API response"
```

---

### Task 3: Frontend type and template

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/views/ImagesListConverter.vue`

- [ ] **Step 1: Add `duplicates_removed` to `ImageItem` interface**

In `frontend/src/types/api.ts`, add the field:

```typescript
export interface ImageItem {
  name: string | null
  version: string | null
  missing_components: boolean
  missing_name: boolean
  missing_version: boolean
  missing_properties: boolean
  duplicates_removed: number
}
```

- [ ] **Step 2: Add column "Удалено дублей" to the table**

In `frontend/src/views/ImagesListConverter.vue`:

In `<thead>` add after the last `<th>`:
```html
<th>Удалено дублей</th>
```

In `<tbody>` add after the last `<td>` in the row:
```html
<td>{{ img.duplicates_removed > 0 ? img.duplicates_removed : '—' }}</td>
```

- [ ] **Step 3: Run frontend type check and tests**

If the project has a frontend type-check command, run it. Run the Vue test suite:

```bash
cd frontend && npx vue-tsc --noEmit && npx vitest run
```

(or the appropriate command from package.json)

Expected: TypeScript compiles cleanly, existing Vue tests pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/views/ImagesListConverter.vue
git commit -m "feat: add duplicates_removed column to images list converter UI"
```
