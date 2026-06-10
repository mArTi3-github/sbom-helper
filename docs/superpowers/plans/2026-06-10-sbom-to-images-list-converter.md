# SBOM-to-images-list Converter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new "SBOM-to-images-list Converter" tool that transforms CycloneDX SBOM files into a machine-readable list of Docker container images.

**Architecture:** New `ImagesListConverter` module in `sbom/` handles all conversion logic (find containers, promote to top-level, build ImageInfo metadata). A new API endpoint `POST /api/v1/convert/images-list` exposes the converter. A new HTML template `images-list-converter.html` provides the web UI with drag-and-drop upload, results table, and download.

**Tech Stack:** Python 3.12, FastAPI, Jinja2, Vanilla JS

---

### Task 1: Core converter module — `sbom/images_list_converter.py`

**Files:**
- Create: `src/purl_resolver/sbom/images_list_converter.py`
- Test: `tests/test_images_list_converter.py`

- [ ] **Step 1: Write the failing tests for `ImagesListConverter`**

```python
from __future__ import annotations

import json
import pytest
from purl_resolver.sbom.images_list_converter import (
    ImagesListConverter,
    ImageInfo,
    ImagesListConversionResult,
)
from purl_resolver.sbom.parser import SbomParseError


class TestImagesListConverter:
    def test_already_valid_images_list(self) -> None:
        """All top-level components have type=container → no transformation"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {
                    "type": "application",
                    "name": "product",
                    "version": "1.0",
                    "manufacturer": {"name": "Acme"},
                },
            },
            "components": [
                {
                    "type": "container",
                    "name": "manager",
                    "version": "3.0.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "yes"},
                    ],
                    "components": [
                        {"type": "library", "name": "lib", "version": "1.0"}
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is False
        assert len(result.images) == 1
        assert result.images[0].name == "manager"
        assert result.images[0].version == "3.0.0"

    def test_containers_inside_nested_are_promoted(self) -> None:
        """Container components nested inside non-container parents are promoted to top-level"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "application",
                    "name": "app",
                    "version": "1.0",
                    "components": [
                        {
                            "type": "container",
                            "name": "gateway",
                            "version": "2.0",
                            "properties": [
                                {"name": "GOST:attack_surface", "value": "yes"},
                                {"name": "GOST:security_function", "value": "no"},
                            ],
                        }
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert len(result.images_list["components"]) == 1
        assert result.images_list["components"][0]["name"] == "gateway"

    def test_no_containers_returns_empty_components(self) -> None:
        """SBOM with zero container components → empty components list"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": "lib-a", "version": "1.0"}
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert result.images_list["components"] == []

    def test_non_container_top_level_removed(self) -> None:
        """Non-container top-level components are removed after promotion"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "library", "name": "lib-a", "version": "1.0"},
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                },
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.was_transformed is True
        assert len(result.images_list["components"]) == 1
        assert result.images_list["components"][0]["name"] == "web"

    def test_missing_name_flag(self) -> None:
        """Container with missing 'name' triggers missing_name flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_name is True

    def test_missing_version_flag(self) -> None:
        """Container with missing 'version' triggers missing_version flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_version is True

    def test_missing_properties_flag(self) -> None:
        """Container with missing 'properties' triggers missing_properties flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0"}
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_properties is True

    def test_missing_components_flag(self) -> None:
        """Container with no nested 'components' triggers missing_components flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_components is True

    def test_metadata_preserved_as_is(self) -> None:
        """Root metadata is not modified"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "metadata": {
                "timestamp": "2024-01-01T00:00:00",
                "component": {
                    "type": "application",
                    "name": "My Product",
                    "version": "72.15",
                    "manufacturer": {"name": "ООО «Ромашка»"},
                },
            },
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images_list["metadata"]["component"]["name"] == "My Product"

    def test_version_not_incremented(self) -> None:
        """Root version field stays unchanged (unlike SBOM enrichment)"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 5,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images_list["version"] == 5

    def test_invalid_json_not_dict_raises_error(self) -> None:
        """Non-dict input raises SbomParseError"""
        with pytest.raises(SbomParseError, match="JSON object"):
            ImagesListConverter.convert([])

    def test_missing_bom_format_raises_error(self) -> None:
        """Missing bomFormat raises SbomParseError"""
        with pytest.raises(SbomParseError, match="bomFormat"):
            ImagesListConverter.convert({"specVersion": "1.6", "components": []})

    def test_wrong_bom_format_raises_error(self) -> None:
        """Wrong bomFormat raises SbomParseError"""
        with pytest.raises(SbomParseError, match="bomFormat"):
            ImagesListConverter.convert({"bomFormat": "SPDX", "components": []})

    def test_empty_name(self) -> None:
        """Container with empty string name triggers missing_name flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "",
                    "version": "1.0",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_name is True

    def test_empty_version(self) -> None:
        """Container with empty string version triggers missing_version flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "",
                    "properties": [
                        {"name": "GOST:attack_surface", "value": "no"},
                        {"name": "GOST:security_function", "value": "no"},
                    ],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_version is True

    def test_empty_properties_array(self) -> None:
        """Container with empty properties array triggers missing_properties flag"""
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {
                    "type": "container",
                    "name": "web",
                    "version": "1.0",
                    "properties": [],
                }
            ],
        }
        result = ImagesListConverter.convert(sbom)
        assert result.images[0].missing_properties is True
```

Run: `pytest tests/test_images_list_converter.py::TestImagesListConverter -v`
Expected: All FAIL with "No module named 'purl_resolver.sbom.images_list_converter'"

- [ ] **Step 2: Write the core implementation**

`src/purl_resolver/sbom/images_list_converter.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ImageInfo:
    name: str | None
    version: str | None
    missing_components: bool = False
    missing_name: bool = False
    missing_version: bool = False
    missing_properties: bool = False


@dataclass
class ImagesListConversionResult:
    images_list: dict
    was_transformed: bool
    images: list[ImageInfo] = field(default_factory=list)


class ImagesListConverter:
    @classmethod
    def convert(cls, sbom_data: object) -> ImagesListConversionResult:
        cls._validate(sbom_data)
        data: dict = sbom_data  # type: ignore[assignment]
        top_components = data.get("components", [])
        if cls._all_are_containers(top_components):
            images = cls._build_image_infos(top_components)
            return ImagesListConversionResult(
                images_list=data, was_transformed=False, images=images
            )

        all_containers = cls._collect_containers(data)
        result_sbom = dict(data)
        result_sbom["components"] = all_containers
        images = cls._build_image_infos(all_containers)
        return ImagesListConversionResult(
            images_list=result_sbom, was_transformed=True, images=images
        )

    @classmethod
    def _validate(cls, data: object) -> None:
        from .parser import CycloneDXParser
        CycloneDXParser.parse(data)

    @classmethod
    def _all_are_containers(cls, components: list) -> bool:
        if not components:
            return False
        return all(
            isinstance(c, dict) and c.get("type") == "container" for c in components
        )

    @classmethod
    def _collect_containers(cls, data: dict) -> list[dict]:
        containers: list[dict] = []
        cls._walk_and_collect(data, containers)
        return containers

    @classmethod
    def _walk_and_collect(cls, obj: object, containers: list[dict]) -> None:
        if isinstance(obj, dict):
            if obj.get("type") == "container":
                containers.append(obj)
                return
            for value in obj.values():
                cls._walk_and_collect(value, containers)
        elif isinstance(obj, list):
            for item in obj:
                cls._walk_and_collect(item, containers)

    @classmethod
    def _build_image_infos(cls, components: list[dict]) -> list[ImageInfo]:
        images: list[ImageInfo] = []
        for comp in components:
            name = comp.get("name")
            version = comp.get("version")
            info = ImageInfo(
                name=name if isinstance(name, str) and name else None,
                version=version if isinstance(version, str) and version else None,
                missing_name=not (isinstance(name, str) and name),
                missing_version=not (isinstance(version, str) and version),
                missing_components=not cls._has_subcomponents(comp),
                missing_properties=not cls._has_properties(comp),
            )
            images.append(info)
        return images

    @classmethod
    def _has_subcomponents(cls, comp: dict) -> bool:
        children = comp.get("components")
        return isinstance(children, list) and len(children) > 0

    @classmethod
    def _has_properties(cls, comp: dict) -> bool:
        props = comp.get("properties")
        return isinstance(props, list) and len(props) > 0
```

- [ ] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_images_list_converter.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/sbom/images_list_converter.py tests/test_images_list_converter.py
git commit -m "feat: add ImagesListConverter core module for SBOM-to-images-list conversion"
```

---

### Task 2: API Route — `routes/images_list.py`

**Files:**
- Create: `src/purl_resolver/routes/images_list.py`
- Test: `tests/test_images_list_converter.py` (add API tests)

- [ ] **Step 1: Write the failing API tests**

Append to `tests/test_images_list_converter.py`:

```python
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from purl_resolver.router import router


class TestImagesListConverterAPI:
    @pytest.fixture
    def client(self) -> TestClient:
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as c:
            yield c

    def test_convert_valid_sbom(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0",
                 "properties": [{"name": "GOST:attack_surface", "value": "no"},
                                {"name": "GOST:security_function", "value": "no"}]}
            ],
        }
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "was_transformed" in data
        assert "images" in data
        assert "images_list" in data

    def test_convert_without_file_returns_422(self, client: TestClient) -> None:
        response = client.post("/api/v1/convert/images-list")
        assert response.status_code == 422

    def test_convert_invalid_json_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("bad.json", b"not json", "application/json")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_json"

    def test_convert_non_cyclonedx_returns_400(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps({"foo": "bar"}), "application/json")},
        )
        assert response.status_code == 400
        data = response.json()
        assert data["error"] == "invalid_sbom"

    def test_convert_response_shape(self, client: TestClient) -> None:
        sbom = {
            "bomFormat": "CycloneDX",
            "specVersion": "1.6",
            "version": 1,
            "components": [
                {"type": "container", "name": "web", "version": "1.0",
                 "properties": [{"name": "GOST:attack_surface", "value": "no"},
                                {"name": "GOST:security_function", "value": "no"}]}
            ],
        }
        response = client.post(
            "/api/v1/convert/images-list",
            files={"file": ("test.json", json.dumps(sbom), "application/json")},
        )
        data = response.json()
        assert isinstance(data["was_transformed"], bool)
        assert isinstance(data["images"], list)
        assert isinstance(data["images_list"], dict)
        if data["images"]:
            img = data["images"][0]
            assert "name" in img
            assert "version" in img
            assert "missing_components" in img
            assert "missing_name" in img
            assert "missing_version" in img
            assert "missing_properties" in img
```

Run: `pytest tests/test_images_list_converter.py::TestImagesListConverterAPI -v`
Expected: FAIL with "No module exists" or route not found

- [ ] **Step 2: Write the API route**

`src/purl_resolver/routes/images_list.py`:

```python
from __future__ import annotations

import json

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse

from ..config import sbom_settings
from ..sbom.images_list_converter import ImagesListConverter
from ..sbom.parser import SbomParseError

router = APIRouter()


@router.post("/api/v1/convert/images-list")
async def convert_images_list(
    request: Request,
    file: UploadFile = File(...),
) -> JSONResponse:
    raw = await file.read()
    if len(raw) > sbom_settings.max_file_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "error": "file_too_large",
                "message": f"File size exceeds maximum of {sbom_settings.max_file_size // (1024*1024)} MB",
            },
        )

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_json", "message": f"Invalid JSON: {e}"},
        )

    try:
        result = ImagesListConverter.convert(data)
    except SbomParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": "invalid_sbom", "message": str(e)},
        )

    return JSONResponse(
        status_code=200,
        content={
            "was_transformed": result.was_transformed,
            "images": [
                {
                    "name": img.name,
                    "version": img.version,
                    "missing_components": img.missing_components,
                    "missing_name": img.missing_name,
                    "missing_version": img.missing_version,
                    "missing_properties": img.missing_properties,
                }
                for img in result.images
            ],
            "images_list": result.images_list,
        },
    )
```

- [ ] **Step 3: Wire the route into `router.py`**

Edit `src/purl_resolver/router.py` — add import and include:

After `from .routes.settings import router as settings_router` add:
```python
from .routes.images_list import router as images_list_router
```

After `router.include_router(settings_router)` add:
```python
router.include_router(images_list_router)
```

- [ ] **Step 4: Run API tests to verify they pass**

Run: `pytest tests/test_images_list_converter.py::TestImagesListConverterAPI -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/images_list.py src/purl_resolver/router.py tests/test_images_list_converter.py
git commit -m "feat: add /api/v1/convert/images-list endpoint"
```

---

### Task 3: Web UI page — `templates/images-list-converter.html`

**Files:**
- Create: `src/purl_resolver/templates/images-list-converter.html`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Write the template**

`src/purl_resolver/templates/images-list-converter.html`:

```html
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Images List Converter — sbom-helper</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #f5f5f5; color: #1a1a1a; line-height: 1.6;
            min-height: 100vh; display: flex; flex-direction: column;
        }
        .container { max-width: 960px; margin: 0 auto; padding: 2rem 1rem; flex: 1; }
        h1 { font-size: 1.5rem; margin-bottom: 0.25rem; }
        .subtitle { color: #666; margin-bottom: 1.5rem; }
        .upload-area {
            background: #fff; border: 2px dashed #ccc; border-radius: 8px;
            padding: 2rem; text-align: center; cursor: pointer;
            transition: border-color 0.2s;
        }
        .upload-area:hover, .upload-area.dragover { border-color: #2563eb; }
        .upload-area input[type="file"] { display: none; }
        .upload-label { font-size: 1rem; color: #555; cursor: pointer; }
        .upload-label strong { color: #2563eb; }
        .upload-hint { font-size: 0.8rem; color: #999; margin-top: 0.5rem; }
        button {
            padding: 0.75rem 1.5rem; background: #2563eb; color: #fff;
            border: none; border-radius: 6px; font-size: 1rem; cursor: pointer;
        }
        button:hover { background: #1d4ed8; }
        button:disabled { background: #93c5fd; cursor: not-allowed; }
        .toolbar { margin-top: 1rem; display: flex; gap: 0.5rem; align-items: center; }
        .status-card {
            background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
            padding: 1rem; margin-top: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        .status-ok { border-left: 4px solid #166534; }
        .status-transformed { border-left: 4px solid #b45309; }
        .status-icon { font-size: 1.2rem; margin-right: 0.5rem; }
        table {
            width: 100%; border-collapse: collapse; margin-top: 1rem;
            background: #fff; border-radius: 8px; overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
        }
        th, td { padding: 0.75rem 1rem; text-align: left; border-bottom: 1px solid #e5e7eb; }
        th { background: #f9fafb; font-size: 0.8rem; text-transform: uppercase; color: #888; }
        .flag-present { color: #991b1b; font-weight: 500; }
        .spinner {
            display: inline-block; width: 1.25rem; height: 1.25rem;
            border: 2px solid #e5e7eb; border-top-color: #2563eb;
            border-radius: 50%; animation: spin 0.6s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }
        .loading { display: flex; align-items: center; gap: 0.5rem; margin-top: 1rem; color: #666; }
        .error-msg {
            background: #fee2e2; border: 1px solid #fecaca; border-radius: 6px;
            padding: 1rem; color: #991b1b; margin-top: 1rem;
        }
        .file-name { font-size: 0.9rem; color: #555; margin-top: 0.5rem; }
        footer { text-align: center; padding: 1rem; color: #999; font-size: 0.8rem; }
    </style>
</head>
<body>
    <div class="container">
        <div style="margin-bottom:1rem;display:flex;gap:1rem;flex-wrap:wrap;">
            <a href="/" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">PURL Resolver</a>
            <a href="/sbom-updater" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">SBOM Updater</a>
            <a href="/db-admin" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Database Admin</a>
            <a href="/settings" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Settings</a>
            <a href="/images-list-converter" style="text-decoration:none;color:inherit;font-weight:600;font-size:0.9rem;">Images List Converter</a>
        </div>
        <h1>Images List Converter</h1>
        <p class="subtitle">Загрузите CycloneDX SBOM (JSON), чтобы сформировать машиночитаемый список docker-образов продукта</p>

        <div id="upload-area" class="upload-area">
            <input type="file" id="file-input" accept=".json">
            <label for="file-input" class="upload-label">
                <strong>Выберите файл</strong> или перетащите его сюда
            </label>
            <div class="upload-hint">CycloneDX JSON, до 200 МБ</div>
            <div id="file-name" class="file-name"></div>
        </div>

        <div class="toolbar">
            <button id="convert-btn" disabled>Конвертировать</button>
        </div>

        <div id="loading" class="loading" style="display:none;">
            <span class="spinner"></span> Обработка SBOM...
        </div>

        <div id="error" class="error-msg" style="display:none;"></div>

        <div id="results" style="display:none;">
            <div id="status-card" class="status-card"></div>
            <div style="overflow-x:auto;">
                <table>
                    <thead>
                        <tr>
                            <th>Имя образа</th>
                            <th>Версия</th>
                            <th>Отсутствуют компоненты</th>
                            <th>Не заполнено поле name</th>
                            <th>Не заполнено поле version</th>
                            <th>Не заполнено поле properties</th>
                        </tr>
                    </thead>
                    <tbody id="results-body"></tbody>
                </table>
            </div>
            <div class="toolbar">
                <button id="download-btn">Скачать список образов</button>
            </div>
        </div>
    </div>

    <footer>Powered by sbom-helper</footer>

    <script>
        const uploadArea = document.getElementById("upload-area");
        const fileInput = document.getElementById("file-input");
        const fileNameDisplay = document.getElementById("file-name");
        const convertBtn = document.getElementById("convert-btn");
        const loading = document.getElementById("loading");
        const errorDiv = document.getElementById("error");
        const resultsDiv = document.getElementById("results");
        const statusCard = document.getElementById("status-card");
        const resultsBody = document.getElementById("results-body");
        const downloadBtn = document.getElementById("download-btn");

        let imagesListData = null;
        let currentFileName = "";

        ["dragenter", "dragover", "dragleave", "drop"].forEach(event => {
            uploadArea.addEventListener(event, e => { e.preventDefault(); e.stopPropagation(); });
        });
        ["dragenter", "dragover"].forEach(event => {
            uploadArea.addEventListener(event, () => uploadArea.classList.add("dragover"));
        });
        ["dragleave", "drop"].forEach(event => {
            uploadArea.addEventListener(event, () => uploadArea.classList.remove("dragover"));
        });
        uploadArea.addEventListener("drop", e => {
            const files = e.dataTransfer.files;
            if (files.length) handleFile(files[0]);
        });
        uploadArea.addEventListener("click", () => fileInput.click());
        fileInput.addEventListener("change", () => {
            if (fileInput.files.length) handleFile(fileInput.files[0]);
        });

        function handleFile(file) {
            currentFileName = file.name;
            fileNameDisplay.textContent = "File: " + file.name + " (" + formatSize(file.size) + ")";
            convertBtn.disabled = false;
        }

        function formatSize(bytes) {
            if (bytes < 1024) return bytes + " B";
            if (bytes < 1048576) return (bytes / 1024).toFixed(1) + " KB";
            return (bytes / 1048576).toFixed(1) + " MB";
        }

        convertBtn.addEventListener("click", async () => {
            const file = fileInput.files[0];
            if (!file) return;

            errorDiv.style.display = "none";
            resultsDiv.style.display = "none";
            loading.style.display = "flex";
            convertBtn.disabled = true;

            const formData = new FormData();
            formData.append("file", file);

            try {
                const res = await fetch("/api/v1/convert/images-list", {
                    method: "POST",
                    body: formData,
                });
                const data = await res.json();

                if (!res.ok) {
                    showError(data.message || data.detail?.message || "Unknown error");
                    return;
                }

                imagesListData = data.images_list;
                renderResults(data);
            } catch {
                showError("Network error: could not reach the server.");
            } finally {
                loading.style.display = "none";
                convertBtn.disabled = false;
            }
        });

        function showError(msg) {
            errorDiv.textContent = msg;
            errorDiv.style.display = "block";
        }

        function renderResults(data) {
            if (data.was_transformed) {
                statusCard.className = "status-card status-transformed";
                statusCard.innerHTML = `<span class="status-icon">&#9888;</span> <strong>Выполнено преобразование</strong> &mdash; исходный SBOM был преобразован в список образов контейнеров.`;
            } else {
                statusCard.className = "status-card status-ok";
                statusCard.innerHTML = `<span class="status-icon">&#10003;</span> <strong>Преобразований не требуется</strong> &mdash; переданный файл уже является корректным списком образов.`;
            }

            resultsBody.innerHTML = data.images.map(img => {
                return `<tr>
                    <td>${escapeHtml(img.name || "&mdash;")}</td>
                    <td>${escapeHtml(img.version || "&mdash;")}</td>
                    <td>${img.missing_components ? '<span class="flag-present">&#10007;</span>' : ""}</td>
                    <td>${img.missing_name ? '<span class="flag-present">&#10007;</span>' : ""}</td>
                    <td>${img.missing_version ? '<span class="flag-present">&#10007;</span>' : ""}</td>
                    <td>${img.missing_properties ? '<span class="flag-present">&#10007;</span>' : ""}</td>
                </tr>`;
            }).join("");

            resultsDiv.style.display = "block";
        }

        downloadBtn.addEventListener("click", () => {
            if (!imagesListData) return;
            const blob = new Blob([JSON.stringify(imagesListData, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = currentFileName.replace(/\.json$/, "") + "_images_list.json";
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        });

        function escapeHtml(str) {
            const div = document.createElement("div");
            div.textContent = str;
            return div.innerHTML;
        }
    </script>
</body>
</html>
```

- [ ] **Step 2: Add the page route to `router.py`**

Edit `src/purl_resolver/router.py` — add after the `db_admin_page` handler:

```python
@router.get("/images-list-converter", response_class=HTMLResponse)
async def images_list_converter_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="images-list-converter.html")
```

Update nav-bars in all existing templates (`index.html`, `sbom.html`, `db-admin.html`, `settings.html`) to include the new link:
```html
<a href="/images-list-converter" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Images List Converter</a>
```

- [ ] **Step 3: Test the full flow**

Run: `pytest tests/test_images_list_converter.py -v`
Expected: All tests PASS (unit + API)

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/templates/images-list-converter.html src/purl_resolver/router.py
git commit -m "feat: add Images List Converter web UI page"
```

---

### Step 5: Update nav-bars in existing templates

- [ ] **Step 5.1: Add link to `index.html`**

Read `src/purl_resolver/templates/index.html`, find the nav-bar `<div>`, and add:
```html
<a href="/images-list-converter" style="color:#2563eb;text-decoration:none;font-size:0.9rem;">Images List Converter</a>
```

- [ ] **Step 5.2: Add link to `sbom.html`**

Same as above — find the nav-bar and add the link.

- [ ] **Step 5.3: Add link to `db-admin.html`**

Same as above.

- [ ] **Step 5.4: Add link to `settings.html`**

Same as above.

- [ ] **Step 5.5: Commit**

```bash
git add src/purl_resolver/templates/index.html src/purl_resolver/templates/sbom.html src/purl_resolver/templates/db-admin.html src/purl_resolver/templates/settings.html
git commit -m "feat: add Images List Converter link to all nav-bars"
```

---

### Task 4: Final verification

- [ ] **Step 1: Run all tests to check nothing is broken**

```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/ -v
```

Expected: All existing tests pass, plus the new converter tests pass.

- [ ] **Step 2: Run lint/type check**

```bash
cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m ruff check src/ tests/
```

Expected: No lint errors. If errors in new files, fix them.