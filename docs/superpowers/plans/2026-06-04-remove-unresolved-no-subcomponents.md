# Remove Unresolved Components Without Subcomponents — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an opt-in option to remove unresolved SBOM components that have no subcomponents.

**Architecture:** New `remover.py` module handles removal logic. Collector gains `has_subcomponents` field. Pipeline, router, reporter, and UI integrate the option as a form parameter with default `false`.

**Tech Stack:** Python, FastAPI, pytest, Jinja2 templates, vanilla JS frontend

---

### Task 1: Add `has_subcomponents` to `SbomComponent`

**Files:**
- Modify: `src/purl_resolver/sbom/collector.py`
- Test: `tests/test_sbom_collector.py`

- [ ] **Step 1: Add field to dataclass**

In `src/purl_resolver/sbom/collector.py`, add `has_subcomponents: bool = False` to the `SbomComponent` dataclass (after `needs_enrichment`):

```python
@dataclass
class SbomComponent:
    name: str
    version: str
    purl: str
    path: _COMPONENT_PATH
    needs_enrichment: bool
    has_subcomponents: bool = False
    existing_references: list[dict] = field(default_factory=list)
```

- [ ] **Step 2: Compute `has_subcomponents` in `_collect()`**

In `_collect()`, after computing `needs`, add:

```python
nested = comp.get("components")
has_subs = isinstance(nested, list) and len(nested) > 0
```

And pass `has_subcomponents=has_subs` to the `SbomComponent` constructor:

```python
accumulator.append(
    SbomComponent(
        name=comp.get("name", ""),
        version=comp.get("version", ""),
        purl=purl,
        path=current_path,
        needs_enrichment=needs,
        has_subcomponents=has_subs,
        existing_references=list(existing),
    )
)
```

- [ ] **Step 3: Write failing tests for `has_subcomponents`**

Add to `tests/test_sbom_collector.py`:

```python
def test_has_subcomponents_true_when_nested_components_present(self) -> None:
    sbom = {
        "components": [
            {
                "type": "application",
                "name": "app",
                "version": "1.0",
                "purl": "pkg:generic/app@1.0",
                "components": [
                    {
                        "type": "library",
                        "name": "sub",
                        "version": "0.5",
                        "purl": "pkg:pypi/sub@0.5",
                    }
                ],
            }
        ]
    }
    result = collect_components(sbom)
    app = next(c for c in result if c.purl == "pkg:generic/app@1.0")
    assert app.has_subcomponents is True

def test_has_subcomponents_false_when_no_nested_components(self) -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False

def test_has_subcomponents_false_when_empty_components_list(self) -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
                "components": [],
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False

def test_has_subcomponents_false_when_components_not_a_list(self) -> None:
    sbom = {
        "components": [
            {
                "type": "library",
                "name": "lib-a",
                "version": "1.0",
                "purl": "pkg:pypi/lib-a@1.0",
                "components": "not-a-list",
            }
        ]
    }
    result = collect_components(sbom)
    assert result[0].has_subcomponents is False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sbom_collector.py -v`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/collector.py tests/test_sbom_collector.py
git commit -m "feat: add has_subcomponents field to SbomComponent"
```

---

### Task 2: Create `remover.py` module

**Files:**
- Create: `src/purl_resolver/sbom/remover.py`
- Test: `tests/test_sbom_remover.py` (NEW)

- [ ] **Step 1: Write failing tests for remover**

Create `tests/test_sbom_remover.py`:

```python
from __future__ import annotations

from purl_resolver.sbom.collector import SbomComponent
from purl_resolver.sbom.remover import remove_unresolved_components


def _comp(
    name: str,
    purl: str,
    path: tuple,
    needs_enrichment: bool = True,
    has_subcomponents: bool = False,
) -> SbomComponent:
    return SbomComponent(
        name=name,
        version="1.0",
        purl=purl,
        path=path,
        needs_enrichment=needs_enrichment,
        has_subcomponents=has_subcomponents,
    )


class TestRemoveUnresolvedComponents:
    def test_removes_unresolved_without_subcomponents(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
                {"type": "library", "name": "b", "version": "2.0", "purl": "pkg:pypi/b@2.0"},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0)),
            _comp("b", "pkg:pypi/b@2.0", ("components", 1)),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "a"
        assert len(removed) == 1
        assert removed[0]["purl"] == "pkg:pypi/b@2.0"

    def test_keeps_unresolved_with_subcomponents(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "application",
                    "name": "parent",
                    "version": "1.0",
                    "purl": "pkg:generic/parent@1.0",
                    "components": [
                        {"type": "library", "name": "child", "version": "1.0", "purl": "pkg:pypi/child@1.0"},
                    ],
                }
            ]
        }
        components = [
            _comp("parent", "pkg:generic/parent@1.0", ("components", 0), has_subcomponents=True),
            _comp("child", "pkg:pypi/child@1.0", ("components", 0, "components", 0)),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "parent"
        assert len(removed) == 0

    def test_removes_child_but_keeps_parent_with_subcomponents(self) -> None:
        sbom = {
            "components": [
                {
                    "type": "application",
                    "name": "parent",
                    "version": "1.0",
                    "purl": "pkg:generic/parent@1.0",
                    "components": [
                        {"type": "library", "name": "resolved-child", "version": "1.0", "purl": "pkg:pypi/rc@1.0"},
                        {"type": "library", "name": "unresolved-child", "version": "1.0", "purl": "pkg:pypi/uc@1.0"},
                    ],
                }
            ]
        }
        components = [
            _comp("parent", "pkg:generic/parent@1.0", ("components", 0), has_subcomponents=True),
            _comp("resolved-child", "pkg:pypi/rc@1.0", ("components", 0, "components", 0)),
            _comp("unresolved-child", "pkg:pypi/uc@1.0", ("components", 0, "components", 1)),
        ]
        resolved = {"pkg:pypi/rc": "https://example.com/rc"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert sbom["components"][0]["name"] == "parent"
        assert len(sbom["components"][0]["components"]) == 1
        assert sbom["components"][0]["components"][0]["name"] == "resolved-child"
        assert len(removed) == 1
        assert removed[0]["purl"] == "pkg:pypi/uc@1.0"

    def test_no_removal_when_all_resolved(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0)),
        ]
        resolved = {"pkg:pypi/a": "https://example.com/a"}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert len(removed) == 0

    def test_no_removal_when_enrichment_not_needed(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0",
                 "externalReferences": [{"type": "vcs", "url": "https://example.com/a"}]},
            ]
        }
        components = [
            _comp("a", "pkg:pypi/a@1.0", ("components", 0), needs_enrichment=False),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert len(sbom["components"]) == 1
        assert len(removed) == 0

    def test_removed_list_contains_name_and_version(self) -> None:
        sbom = {
            "components": [
                {"type": "library", "name": "special", "version": "3.2.1", "purl": "pkg:pypi/special@3.2.1"},
            ]
        }
        components = [
            _comp("special", "pkg:pypi/special@3.2.1", ("components", 0)),
        ]
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert removed[0] == {"purl": "pkg:pypi/special@3.2.1", "name": "special", "version": "3.2.1"}

    def test_empty_components_list(self) -> None:
        sbom = {"components": []}
        components: list[SbomComponent] = []
        resolved: dict[str, str] = {}
        removed = remove_unresolved_components(sbom, components, resolved)
        assert removed == []
        assert sbom["components"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_sbom_remover.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'purl_resolver.sbom.remover'`

- [ ] **Step 3: Implement `remover.py`**

Create `src/purl_resolver/sbom/remover.py`:

```python
from __future__ import annotations

from .collector import SbomComponent
from ..purl_utils import safe_normalize


def remove_unresolved_components(
    sbom: dict,
    components: list[SbomComponent],
    resolved: dict[str, str],
) -> list[dict]:
    to_remove = [
        c for c in components
        if c.needs_enrichment
        and not c.has_subcomponents
        and safe_normalize(c.purl) not in resolved
    ]

    to_remove.sort(key=lambda c: c.path, reverse=True)

    removed: list[dict] = []
    for comp in to_remove:
        obj: object = sbom
        for k in comp.path[:-1]:
            if isinstance(k, int):
                assert isinstance(obj, list)
                obj = obj[k]
            else:
                assert isinstance(obj, dict)
                obj = obj[k]

        idx = comp.path[-1]
        if isinstance(idx, int) and isinstance(obj, list):
            obj.pop(idx)
            removed.append({"purl": comp.purl, "name": comp.name, "version": comp.version})

    return removed
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_sbom_remover.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/remover.py tests/test_sbom_remover.py
git commit -m "feat: add remover module for unresolved SBOM components"
```

---

### Task 3: Update reporter to include `removed` in report

**Files:**
- Modify: `src/purl_resolver/sbom/reporter.py`
- Test: `tests/test_sbom_reporter.py`

- [ ] **Step 1: Add `removed` parameter to `build_report()`**

In `src/purl_resolver/sbom/reporter.py`, change the function signature and body:

```python
def build_report(
    components: list[SbomComponent],
    resolved: dict[str, str],
    skipped: int = 0,
    removed: list[dict] | None = None,
) -> dict:
    if removed is None:
        removed = []
    seen: set[str] = set()
    results: list[dict] = []
    found_count = 0
    not_found_count = 0

    for comp in components:
        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        if key in seen:
            continue
        seen.add(key)
        repo_url = resolved.get(key)
        if repo_url is not None:
            found_count += 1
            results.append({"purl": key, "status": "found", "repository_url": repo_url})
        else:
            not_found_count += 1
            results.append({"purl": key, "status": "not_found", "repository_url": None})

    for r in removed:
        results.append({
            "purl": r["purl"],
            "status": "removed",
            "repository_url": None,
            "name": r["name"],
            "version": r["version"],
        })

    return {
        "summary": {
            "total_purls": found_count + not_found_count,
            "found": found_count,
            "not_found": not_found_count,
            "skipped": skipped,
            "removed": len(removed),
        },
        "results": results,
    }
```

- [ ] **Step 2: Write tests for `removed` in reporter**

Add to `tests/test_sbom_reporter.py`:

```python
def test_removed_count_in_summary(self) -> None:
    components = [
        SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
    ]
    resolved = {"pkg:pypi/a": "https://example.com/a"}
    removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
    report = build_report(components, resolved, skipped=0, removed=removed)
    assert report["summary"]["removed"] == 1
    assert report["summary"]["found"] == 1

def test_removed_entries_in_results(self) -> None:
    components = [
        SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
    ]
    resolved = {"pkg:pypi/a": "https://example.com/a"}
    removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
    report = build_report(components, resolved, skipped=0, removed=removed)
    removed_results = [r for r in report["results"] if r["status"] == "removed"]
    assert len(removed_results) == 1
    assert removed_results[0]["purl"] == "pkg:pypi/b@2"
    assert removed_results[0]["name"] == "b"
    assert removed_results[0]["version"] == "2"

def test_no_removed_when_empty_list(self) -> None:
    components = [
        SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
    ]
    resolved = {"pkg:pypi/a": "https://example.com/a"}
    report = build_report(components, resolved, skipped=0, removed=[])
    assert report["summary"]["removed"] == 0
    assert all(r["status"] != "removed" for r in report["results"])

def test_no_removed_when_parameter_omitted(self) -> None:
    components = [
        SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
    ]
    resolved = {"pkg:pypi/a": "https://example.com/a"}
    report = build_report(components, resolved, skipped=0)
    assert report["summary"]["removed"] == 0
```

- [ ] **Step 3: Run all reporter tests**

Run: `.venv/bin/pytest tests/test_sbom_reporter.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/sbom/reporter.py tests/test_sbom_reporter.py
git commit -m "feat: add removed count and entries to SBOM report"
```

---

### Task 4: Integrate remover into pipeline

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py`
- Modify: `src/purl_resolver/service.py` (update `process_sbom` signature)
- Test: `tests/test_sbom_enricher.py`

- [ ] **Step 1: Update `process_sbom()` in `service.py`**

In `src/purl_resolver/service.py`, add `removed` parameter:

```python
def process_sbom(
    sbom: dict,
    components: list,
    resolved: dict[str, str],
    skipped: int = 0,
    removed: list[dict] | None = None,
) -> dict:
    enrich_sbom(sbom, components, resolved)
    return build_report(components, resolved, skipped=skipped, removed=removed or [])
```

- [ ] **Step 2: Update `SbomEnrichmentPipeline.process()`**

In `src/purl_resolver/sbom_enrichment.py`:

Add import:
```python
from .sbom.remover import remove_unresolved_components
```

Update `process()` signature and body:

```python
async def process(
    self,
    sbom_data: dict,
    remove_unresolved_no_subcomponents: bool = False,
) -> SbomEnrichmentResult:
    """Parse, collect, deduplicate, resolve, enrich, and report."""
    CycloneDXParser.parse(sbom_data)

    components = collect_components(sbom_data)
    purls_to_resolve = [c for c in components if c.needs_enrichment]

    seen: set[str] = set()
    unique_purls: list[str] = []
    skipped = 0
    for comp in purls_to_resolve:
        n = safe_normalize(comp.purl)
        if n == comp.purl:
            skipped += 1
            continue
        if n not in seen:
            seen.add(n)
            unique_purls.append(comp.purl)

    resolved = await resolve_batch(
        unique_purls,
        self._storage,
        self._resolvers,
        settings_store=self._settings_store,
        resolver="import-sbom",
    )
    await store_preexisting_references(
        components, self._storage, resolver="import-sbom"
    )

    removed: list[dict] = []
    if remove_unresolved_no_subcomponents:
        removed = remove_unresolved_components(sbom_data, components, resolved)

    report = process_sbom(sbom_data, components, resolved, skipped=skipped, removed=removed)

    return SbomEnrichmentResult(
        report=report,
        enriched_sbom=sbom_data,
    )
```

- [ ] **Step 3: Write test for `process_sbom` with `removed`**

Add to `tests/test_sbom_enricher.py`:

```python
def test_process_sbom_passes_removed_to_report(self) -> None:
    from purl_resolver.service import process_sbom
    sbom = {
        "version": 1,
        "metadata": {"timestamp": "2024-01-01T00:00:00"},
        "components": [
            {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
        ],
    }
    components = collect_components(sbom)
    resolved = {"pkg:pypi/a": "https://github.com/example/a"}
    removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
    report = process_sbom(sbom, components, resolved, skipped=0, removed=removed)
    assert report["summary"]["removed"] == 1
    assert any(r["status"] == "removed" for r in report["results"])
```

- [ ] **Step 4: Run all enricher tests**

Run: `.venv/bin/pytest tests/test_sbom_enricher.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom_enrichment.py src/purl_resolver/service.py tests/test_sbom_enricher.py
git commit -m "feat: integrate remover into SBOM enrichment pipeline"
```

---

### Task 5: Add form parameter to API endpoint

**Files:**
- Modify: `src/purl_resolver/router.py`
- Test: `tests/test_sbom_integration.py`

- [ ] **Step 1: Add form parameter to endpoint**

In `src/purl_resolver/router.py`, add `Form` import (already imported) and update `resolve_sbom_endpoint`:

```python
@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
) -> JSONResponse:
```

Update the pipeline call:

```python
result = await pipeline.process(data, remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents)
```

- [ ] **Step 2: Write integration test for the new parameter**

Add to `tests/test_sbom_integration.py`:

```python
def test_remove_unresolved_no_subcomponents_removes_components(
    self, client: TestClient
) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": "2024-01-01T00:00:00",
            "component": {"type": "application", "name": "app", "version": "1.0"},
        },
        "components": [
            {
                "type": "library",
                "name": "certifi",
                "version": "2026.1.4",
                "purl": "pkg:pypi/certifi@2026.1.4",
            },
            {
                "type": "library",
                "name": "unknown",
                "version": "1.0",
                "purl": "pkg:pypi/unknown-pkg@1.0",
            },
        ],
    }
    response = client.post(
        "/api/v1/resolve/sbom",
        data={"remove_unresolved_no_subcomponents": "true"},
        files={"file": ("test.json", json.dumps(sbom), "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["removed"] == 1
    removed_results = [r for r in data["results"] if r["status"] == "removed"]
    assert len(removed_results) == 1
    assert removed_results[0]["purl"] == "pkg:pypi/unknown-pkg"
    enriched = data["enriched_sbom"]
    assert len(enriched["components"]) == 1
    assert enriched["components"][0]["name"] == "certifi"

def test_remove_unresolved_keeps_parent_with_subcomponents(
    self, client: TestClient
) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": "2024-01-01T00:00:00",
            "component": {"type": "application", "name": "app", "version": "1.0"},
        },
        "components": [
            {
                "type": "application",
                "name": "parent-pkg",
                "version": "1.0",
                "purl": "pkg:generic/parent-pkg@1.0",
                "components": [
                    {
                        "type": "library",
                        "name": "certifi",
                        "version": "2026.1.4",
                        "purl": "pkg:pypi/certifi@2026.1.4",
                    },
                ],
            },
        ],
    }
    response = client.post(
        "/api/v1/resolve/sbom",
        data={"remove_unresolved_no_subcomponents": "true"},
        files={"file": ("test.json", json.dumps(sbom), "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    enriched = data["enriched_sbom"]
    assert len(enriched["components"]) == 1
    assert enriched["components"][0]["name"] == "parent-pkg"

def test_default_false_preserves_current_behavior(
    self, client: TestClient
) -> None:
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": "2024-01-01T00:00:00",
            "component": {"type": "application", "name": "app", "version": "1.0"},
        },
        "components": [
            {
                "type": "library",
                "name": "unknown",
                "version": "1.0",
                "purl": "pkg:pypi/unknown-pkg@1.0",
            },
        ],
    }
    response = client.post(
        "/api/v1/resolve/sbom",
        files={"file": ("test.json", json.dumps(sbom), "application/json")},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["removed"] == 0
    assert data["summary"]["not_found"] == 1
    enriched = data["enriched_sbom"]
    assert len(enriched["components"]) == 1
```

- [ ] **Step 3: Run all integration tests**

Run: `.venv/bin/pytest tests/test_sbom_integration.py -v`
Expected: All tests PASS

- [ ] **Step 4: Run full test suite**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/router.py tests/test_sbom_integration.py
git commit -m "feat: add remove_unresolved_no_subcomponents form parameter to API"
```

---

### Task 6: Update web UI with checkbox and removed display

**Files:**
- Modify: `src/purl_resolver/templates/sbom.html`

- [ ] **Step 1: Add checkbox to toolbar**

In `src/purl_resolver/templates/sbom.html`, inside the `<div class="toolbar">`, add a checkbox before the process button:

```html
<div class="toolbar">
    <label style="display:flex;align-items:center;gap:0.4rem;font-size:0.9rem;color:#555;cursor:pointer;">
        <input type="checkbox" id="remove-unresolved">
        Удалять ненайденные компоненты без подкомпонентов
    </label>
    <button id="process-btn" disabled>Обработать</button>
</div>
```

- [ ] **Step 2: Pass checkbox value in FormData**

In the `processBtn` click handler, after creating `formData`, add:

```javascript
const removeCheckbox = document.getElementById("remove-unresolved");
if (removeCheckbox.checked) {
    formData.append("remove_unresolved_no_subcomponents", "true");
}
```

- [ ] **Step 3: Add removed display in `renderResults()`**

In the `renderResults()` function, add a `removed` card in the summary grid:

```javascript
function renderResults(data) {
    const s = data.summary;
    summaryBox.innerHTML = `
        <h3 style="margin-bottom:0.5rem;">Результаты</h3>
        <div class="summary-grid">
            <div class="summary-item">
                <div class="summary-value">${s.total_purls}</div>
                <div class="summary-label">Всего PURL</div>
            </div>
            <div class="summary-item">
                <div class="summary-value found">${s.found}</div>
                <div class="summary-label">Найдено</div>
            </div>
            <div class="summary-item">
                <div class="summary-value not-found">${s.not_found}</div>
                <div class="summary-label">Не найдено</div>
            </div>
            ${s.skipped > 0 ? `<div class="summary-item"><div class="summary-value skipped">${s.skipped}</div><div class="summary-label">Пропущено</div></div>` : ""}
            ${s.removed > 0 ? `<div class="summary-item"><div class="summary-value" style="color:#b45309;">${s.removed}</div><div class="summary-label">Удалено</div></div>` : ""}
        </div>
    `;

    resultsBody.innerHTML = data.results.map(r => {
        const statusClass = r.status === "found" ? "status-found" : r.status === "removed" ? "status-removed" : "status-not-found";
        const statusText = r.status === "found" ? "Found" : r.status === "removed" ? "Removed" : "Not found";
        const urlHtml = r.repository_url
            ? `<a href="${escapeHtml(r.repository_url)}" target="_blank">${escapeHtml(r.repository_url)}</a>`
            : "&mdash;";
        return `<tr>
            <td><code>${escapeHtml(r.purl)}</code></td>
            <td class="${statusClass}">${statusText}</td>
            <td class="repo-url-cell">${urlHtml}</td>
        </tr>`;
    }).join("");

    resultsDiv.style.display = "block";
}
```

- [ ] **Step 4: Add CSS for removed status**

In the `<style>` section, add:

```css
.status-removed { color: #b45309; font-weight: 500; }
```

- [ ] **Step 5: Visual verification**

Run the app locally and verify:
1. Checkbox appears in toolbar next to "Обработать"
2. When unchecked, behavior is identical to before
3. When checked, unresolved components without subcomponents are removed and shown in results
4. `removed` card appears in summary when > 0

- [ ] **Step 6: Commit**

```bash
git add src/purl_resolver/templates/sbom.html
git commit -m "feat: add checkbox and removed display to SBOM-updater UI"
```

---

### Task 7: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `.venv/bin/pytest tests/ -v`
Expected: All tests PASS, no regressions

- [ ] **Step 2: Verify no lint issues**

Run: `.venv/bin/python -m py_compile src/purl_resolver/sbom/remover.py && echo OK`
Expected: OK

- [ ] **Step 3: Final commit if needed**
