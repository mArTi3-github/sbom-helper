# SBOM Ignore Patterns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ability to define field-value ignore patterns for SBOM enrichment, persisted to a JSON file, with a UI for management.

**Architecture:** A new `IgnorePatternsStore` handles persistence. Filtering is a new step in the enrichment pipeline that marks matching components as `ignored` before resolution. The reporter surfaces ignored components with a dedicated status. API endpoints manage patterns; the resolve endpoint accepts them as a JSON form field.

**Tech Stack:** Python 3.12+, FastAPI, Jinja2, vanilla JS, pytest

---

## File Structure

```
src/purl_resolver/
├── ignore_patterns_store.py      # NEW — JSON file read/write for patterns
├── sbom/
│   ├── collector.py               # MODIFY — add ignored field to SbomComponent
│   ├── reporter.py                # MODIFY — add ignored status + counter
├── sbom_enrichment.py             # MODIFY — add filtering step
├── routes/
│   ├── resolve.py                 # MODIFY — accept ignore_patterns form field
│   ├── ignore_patterns.py         # NEW — GET/POST endpoints for patterns
├── router.py                      # MODIFY — register ignore_patterns routes
├── templates/
│   ├── sbom.html                  # MODIFY — add patterns UI subsection

data/
├── sbom_components_ignore_patterns.json   # NEW — persisted patterns

tests/
├── test_ignore_patterns_store.py          # NEW
├── test_sbom_ignore_patterns.py           # NEW — integration test
```

---

### Task 1: IgnorePatternsStore

**Files:**
- Create: `src/purl_resolver/ignore_patterns_store.py`
- Test: `tests/test_ignore_patterns_store.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_ignore_patterns_store.py
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from purl_resolver.ignore_patterns_store import IgnorePatternsStore


def test_load_returns_empty_list_when_file_missing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "nonexistent.json"
        store = IgnorePatternsStore(path)
        assert store.load() == []


def test_load_returns_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        data = [{"field": "purl", "pattern": "test"}, {"field": "group", "pattern": "test"}]
        path.write_text(json.dumps(data), encoding="utf-8")
        store = IgnorePatternsStore(path)
        assert store.load() == data


def test_save_writes_patterns():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        store = IgnorePatternsStore(path)
        data = [{"field": "name", "pattern": "test"}]
        store.save(data)
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == data


def test_save_overwrites_existing():
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "patterns.json"
        path.write_text(json.dumps([{"field": "old", "pattern": "old"}]), encoding="utf-8")
        store = IgnorePatternsStore(path)
        store.save([{"field": "new", "pattern": "new"}])
        saved = json.loads(path.read_text(encoding="utf-8"))
        assert saved == [{"field": "new", "pattern": "new"}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_ignore_patterns_store.py -v`
Expected: 4 FAILED (ImportError for IgnorePatternsStore)

- [ ] **Step 3: Write minimal implementation**

```python
# src/purl_resolver/ignore_patterns_store.py
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PATTERNS_FILE_DEFAULT = "./data/sbom_components_ignore_patterns.json"


class IgnorePatternsStore:

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            path = PATTERNS_FILE_DEFAULT
        self._path = Path(path)

    def load(self) -> list[dict[str, str]]:
        if not self._path.exists():
            return []
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            if not isinstance(data, list):
                return []
            return data
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load ignore patterns from %s: %s", self._path, exc)
            return []

    def save(self, patterns: list[dict[str, str]]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(patterns, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_ignore_patterns_store.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/ignore_patterns_store.py tests/test_ignore_patterns_store.py
git commit -m "feat: add IgnorePatternsStore for persisting ignore patterns to JSON"
```

---

### Task 2: Add `ignored` field to SbomComponent

**Files:**
- Modify: `src/purl_resolver/sbom/collector.py`

- [ ] **Step 1: Add the `ignored` field**

Edit `src/purl_resolver/sbom/collector.py`, line 18 (after `existing_references`):

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
    ignored: bool = False
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/test_sbom_collector.py -v`
Expected: all PASSED (default `False` won't break anything)

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/sbom/collector.py
git commit -m "feat: add ignored field to SbomComponent dataclass"
```

---

### Task 3: Add ignore-patterns filtering to pipeline

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py`

- [ ] **Step 1: Add filtering logic**

Add a helper to `sbom_enrichment.py` and integrate it into `process()`.

```python
# At the end of sbom_enrichment.py, before class SbomEnrichmentResult
def _component_matches_any_pattern(
    sbom_data: dict,
    comp: SbomComponent,
    ignore_patterns: list[dict[str, str]],
) -> bool:
    if not ignore_patterns:
        return False
    target: dict = sbom_data
    for segment in comp.path:
        target = target[segment]
    for rule in ignore_patterns:
        field = rule.get("field", "")
        pattern = rule.get("pattern", "")
        if not field or not pattern:
            continue
        value = target.get(field)
        if value is not None and pattern in str(value):
            return True
    return False
```

Update `SbomEnrichmentPipeline.__init__` to accept and store `ignore_patterns_store`:

```python
def __init__(
    self,
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    ignore_patterns_store: IgnorePatternsStore | None = None,
) -> None:
    self._storage = storage
    self._resolvers = resolvers
    self._settings_store = settings_store
    self._ignore_patterns_store = ignore_patterns_store
```

Add import at top of `sbom_enrichment.py`:

```python
from .collector import _SOURCE_REF_TYPES, SbomComponent, collect_components
from .ignore_patterns_store import IgnorePatternsStore
```

Update `process()` signature to accept `ignore_patterns`:

```python
async def process(
    self,
    sbom_data: dict,
    remove_unresolved_no_subcomponents: bool = False,
    validate_existing_refs: bool = False,
    ignore_patterns: list[dict[str, str]] | None = None,
) -> SbomEnrichmentResult:
```

Add the filtering step after the validate existing refs loop (after line ~65):

```python
        # --- Ignore patterns filtering ---
        if ignore_patterns:
            for comp in components:
                if not comp.needs_enrichment:
                    continue
                if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
                    comp.ignored = True
                    comp.needs_enrichment = False
```

This block goes right after the `validate_existing_refs` loop and before:

```python
        purls_to_resolve = [c for c in components if c.needs_enrichment]
```

- [ ] **Step 2: Verify existing tests still pass**

Run: `python -m pytest tests/test_sbom_integration.py tests/test_sbom_enricher.py -v`
Expected: all PASSED

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/sbom_enrichment.py
git commit -m "feat: add ignore-patterns filtering step to enrichment pipeline"
```

---

### Task 4: Update reporter for "ignored" status

**Files:**
- Modify: `src/purl_resolver/sbom/reporter.py`

- [ ] **Step 1: Add ignored handling to `build_report()`**

Replace the function with one that also processes ignored components:

```python
from .collector import SbomComponent
from ..purl_utils import safe_normalize
from ..schemas import ResolveResponse


def build_report(
    components: list[SbomComponent],
    resolved: dict[str, ResolveResponse],
    skipped: int = 0,
    removed: list[dict] | None = None,
) -> dict:
    if removed is None:
        removed = []
    removed_keys = {safe_normalize(r["purl"]) for r in removed}
    seen: set[str] = set()
    results: list[dict] = []
    found_count = 0
    not_found_count = 0
    ignored_count = 0

    for comp in components:
        if comp.ignored:
            ignored_count += 1
            key = safe_normalize(comp.purl)
            if key in seen:
                continue
            seen.add(key)
            results.append({
                "purl": key,
                "status": "ignored",
                "repository_url": None,
                "found_by": "",
                "resolver": "",
                "name": comp.name,
                "version": comp.version,
            })
            continue

        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        if key in seen:
            continue
        seen.add(key)
        if key in removed_keys:
            continue
        resp = resolved.get(key)
        repo_url = resp.repository_url if resp is not None else None
        if repo_url is not None:
            found_count += 1
            results.append({
                "purl": key,
                "status": "found",
                "repository_url": repo_url,
                "found_by": resp.found_by if resp else "",
                "resolver": resp.resolver if resp else "",
            })
        else:
            not_found_count += 1
            results.append({
                "purl": key,
                "status": "not_found",
                "repository_url": None,
                "found_by": "",
                "resolver": "",
            })

    for r in removed:
        results.append({
            "purl": r["purl"],
            "status": "removed",
            "repository_url": None,
            "found_by": "",
            "resolver": "",
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
            "ignored": ignored_count,
        },
        "results": results,
    }
```

- [ ] **Step 2: Run existing reporter tests**

Run: `python -m pytest tests/test_sbom_reporter.py -v`
Expected: all PASSED (backward compatible — no ignored components in existing tests)

- [ ] **Step 3: Write tests for ignored status**

```python
# tests/test_sbom_reporter.py (add these test functions at the end)
from purl_resolver.sbom.collector import SbomComponent


def test_build_report_includes_ignored_components():
    comps = [
        SbomComponent(name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0", path=("components", 0), needs_enrichment=False, ignored=True),
        SbomComponent(name="pkg-b", version="2.0", purl="pkg:pypi/pkg-b@2.0", path=("components", 1), needs_enrichment=True, ignored=False),
    ]
    resolved = {}
    report = build_report(comps, resolved)
    assert report["summary"]["ignored"] == 1
    assert report["summary"]["total_purls"] == 1
    statuses = {r["status"] for r in report["results"]}
    assert "ignored" in statuses
    assert "not_found" in statuses
    ignored = [r for r in report["results"] if r["status"] == "ignored"]
    assert ignored[0]["name"] == "pkg-a"
    assert ignored[0]["version"] == "1.0"


def test_build_report_ignored_not_counted_in_total():
    comps = [
        SbomComponent(name="pkg-a", version="1.0", purl="pkg:pypi/pkg-a@1.0", path=("components", 0), needs_enrichment=False, ignored=True),
    ]
    resolved = {}
    report = build_report(comps, resolved)
    assert report["summary"]["ignored"] == 1
    assert report["summary"]["total_purls"] == 0
    assert report["summary"]["found"] == 0
    assert report["summary"]["not_found"] == 0
```

- [ ] **Step 4: Run updated reporter tests**

Run: `python -m pytest tests/test_sbom_reporter.py -v`
Expected: all PASSED (including new tests)

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/sbom/reporter.py tests/test_sbom_reporter.py
git commit -m "feat: add ignored status to SBOM enrichment report"
```

---

### Task 5: API endpoints for ignore patterns

**Files:**
- Create: `src/purl_resolver/routes/ignore_patterns.py`
- Modify: `src/purl_resolver/router.py`

- [ ] **Step 1: Create routes for GET/POST ignore-patterns**

```python
# src/purl_resolver/routes/ignore_patterns.py
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from pydantic import BaseModel

router = APIRouter()


class IgnorePatternItem(BaseModel):
    field: str
    pattern: str


class IgnorePatternsPayload(BaseModel):
    patterns: list[IgnorePatternItem]


@router.get("/api/v1/sbom/ignore-patterns")
async def get_ignore_patterns(request: Request) -> JSONResponse:
    store = request.app.state.ignore_patterns_store
    patterns = store.load()
    return JSONResponse(content={"patterns": patterns})


@router.post("/api/v1/sbom/ignore-patterns")
async def save_ignore_patterns(
    payload: IgnorePatternsPayload,
    request: Request,
) -> JSONResponse:
    store = request.app.state.ignore_patterns_store
    data = [{"field": p.field, "pattern": p.pattern} for p in payload.patterns]
    store.save(data)
    return JSONResponse(content={"status": "saved"})
```

- [ ] **Step 2: Register routes and wire IgnorePatternsStore in `router.py`**

Edit `src/purl_resolver/router.py`:

```python
from .routes.ignore_patterns import router as ignore_patterns_router
# ... (after other includes)
router.include_router(ignore_patterns_router)
```

Edit `src/purl_resolver/main.py` (the app factory) to instantiate and attach `IgnorePatternsStore`. Let me check how `SettingsStore` is wired.

Read `main.py` to understand the pattern, then add the same for `IgnorePatternsStore`.

First, read main.py to see how SettingsStore is wired.

- [ ] **Step 2a: Read `main.py`**

Run: `cat src/purl_resolver/main.py`

- [ ] **Step 2b: Wire IgnorePatternsStore into app state**

Following the pattern used for `settings_store`:

```python
from .ignore_patterns_store import IgnorePatternsStore

# In the lifespan or startup:
app.state.ignore_patterns_store = IgnorePatternsStore()
```

- [ ] **Step 3: Verify routes work**

Run the server and test:
```bash
curl http://localhost:8000/api/v1/sbom/ignore-patterns
```
Expected: `{"patterns": []}`

```bash
curl -X POST http://localhost:8000/api/v1/sbom/ignore-patterns \
  -H "Content-Type: application/json" \
  -d '{"patterns": [{"field": "purl", "pattern": "test"}]}'
```
Expected: `{"status": "saved"}`

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/routes/ignore_patterns.py src/purl_resolver/router.py src/purl_resolver/main.py
git commit -m "feat: add API endpoints for ignore patterns"
```

---

### Task 6: Modify resolve endpoint to accept ignore_patterns

**Files:**
- Modify: `src/purl_resolver/routes/resolve.py`

- [ ] **Step 1: Add `ignore_patterns` form field to the endpoint**

Edit the `resolve_sbom_endpoint` function:

```python
@router.post("/api/v1/resolve/sbom")
async def resolve_sbom_endpoint(
    request: Request,
    file: UploadFile = File(...),
    remove_unresolved_no_subcomponents: bool = Form(False),
    validate_existing_refs: bool = Form(False),
    ignore_patterns: str = Form(None),
) -> JSONResponse:
```

After parsing the JSON data from the file, parse `ignore_patterns`:

```python
    parsed_patterns: list[dict[str, str]] | None = None
    if ignore_patterns:
        try:
            parsed_patterns = json.loads(ignore_patterns)
            if not isinstance(parsed_patterns, list):
                parsed_patterns = None
        except json.JSONDecodeError:
            parsed_patterns = None
```

Pass to pipeline:

```python
    result = await pipeline.process(
        data,
        remove_unresolved_no_subcomponents=remove_unresolved_no_subcomponents,
        validate_existing_refs=validate_existing_refs,
        ignore_patterns=parsed_patterns,
    )
```

- [ ] **Step 2: Run existing resolve tests**

Run: `python -m pytest tests/test_api.py -v`
Expected: all PASSED

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/routes/resolve.py
git commit -m "feat: pass ignore_patterns to enrichment pipeline from API"
```

---

### Task 7: Frontend UI for ignore patterns

**Files:**
- Modify: `src/purl_resolver/templates/sbom.html`

- [ ] **Step 1: Add CSS for the new subsection**

Add to the `<style>` block (before the closing `</style>` tag):

```css
.ignore-section {
    background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 1rem; margin-top: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.ignore-section h3 { font-size: 1rem; margin-bottom: 0.75rem; }
.ignore-row { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem; }
.ignore-row input[type="text"] {
    padding: 0.4rem 0.6rem; border: 1px solid #d1d5db; border-radius: 4px;
    font-size: 0.9rem; width: 180px;
}
.ignore-row input[type="text"]:focus { outline: none; border-color: #2563eb; }
.ignore-sep { color: #6b7280; font-size: 0.85rem; font-style: italic; }
.status-ignored { color: #6b7280; font-weight: 500; }
```

- [ ] **Step 2: Add the HTML subsection**

Add before the `<div id="loading">` element (after the toolbar div that ends at line 104):

```html
        <div class="ignore-section">
            <h3>Игнорировать компоненты с перечисленными признаками:</h3>
            <div id="patterns-list"></div>
            <button id="save-patterns-btn" style="margin-top:0.75rem;">Сохранить</button>
        </div>
```

- [ ] **Step 3: Add JavaScript logic**

Add to the `<script>` block, before the `enrichedSbom` variable declaration. All new functions go before the existing code.

```javascript
        // --- Ignore patterns UI ---
        const patternsList = document.getElementById("patterns-list");
        const savePatternsBtn = document.getElementById("save-patterns-btn");

        function createPatternRow(fieldVal, patternVal, isLast) {
            const container = document.createElement("div");
            const row = document.createElement("div");
            row.className = "ignore-row";

            const fieldInput = document.createElement("input");
            fieldInput.type = "text";
            fieldInput.placeholder = "поле";
            fieldInput.value = fieldVal || "";
            fieldInput.dataset.role = "field";

            const containsLabel = document.createElement("span");
            containsLabel.textContent = "содержит";

            const patternInput = document.createElement("input");
            patternInput.type = "text";
            patternInput.placeholder = "значение";
            patternInput.value = patternVal || "";
            patternInput.dataset.role = "pattern";

            row.appendChild(fieldInput);
            row.appendChild(containsLabel);
            row.appendChild(patternInput);
            container.appendChild(row);

            if (isLast === false) {
                const sep = document.createElement("div");
                sep.className = "ignore-sep";
                sep.textContent = "или";
                container.appendChild(sep);
            }
            return container;
        }

        function collectPatterns() {
            const rows = patternsList.querySelectorAll(".ignore-row");
            const patterns = [];
            rows.forEach(row => {
                const field = row.querySelector('[data-role="field"]').value.trim();
                const pattern = row.querySelector('[data-role="pattern"]').value.trim();
                if (field && pattern) {
                    patterns.push({field, pattern});
                }
            });
            return patterns;
        }

        function renderPatterns(patterns) {
            patternsList.innerHTML = "";
            const all = patterns || [];
            const hasEmpty = all.length === 0 || all.some(p => !p.field || !p.pattern);
            const items = hasEmpty ? all : [...all, {field: "", pattern: ""}];
            for (let i = 0; i < items.length; i++) {
                const isLast = (i === items.length - 1);
                const el = createPatternRow(items[i].field, items[i].pattern, isLast);
                patternsList.appendChild(el);
            }
            attachAutoAdd();
        }

        function attachAutoAdd() {
            const lastRow = patternsList.querySelector(".ignore-row:last-child");
            if (!lastRow) return;
            const inputs = lastRow.querySelectorAll('input[type="text"]');
            inputs.forEach(inp => {
                inp.removeEventListener("input", onLastRowInput);
                inp.addEventListener("input", onLastRowInput);
            });
        }

        function onLastRowInput() {
            const rows = patternsList.querySelectorAll(".ignore-row");
            const lastRow = rows[rows.length - 1];
            const fields = lastRow.querySelectorAll('input[type="text"]');
            let hasValue = false;
            fields.forEach(f => { if (f.value.trim()) hasValue = true; });
            if (hasValue) {
                const container = createPatternRow("", "", true);
                patternsList.appendChild(container);
                attachAutoAdd();
            }
        }

        // Load patterns on page load
        fetch("/api/v1/sbom/ignore-patterns")
            .then(r => r.json())
            .then(data => renderPatterns(data.patterns))
            .catch(() => renderPatterns([]));

        // Save button
        savePatternsBtn.addEventListener("click", async () => {
            const patterns = collectPatterns();
            try {
                const res = await fetch("/api/v1/sbom/ignore-patterns", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({patterns}),
                });
                if (res.ok) {
                    savePatternsBtn.textContent = "Сохранено";
                    setTimeout(() => { savePatternsBtn.textContent = "Сохранить"; }, 2000);
                }
            } catch {}
        });
```

- [ ] **Step 4: Modify the process button handler to send ignore_patterns**

In the `processBtn.addEventListener("click", ...)` handler, after appending checkboxes to formData, add:

```javascript
            const patterns = collectPatterns();
            if (patterns.length > 0) {
                formData.append("ignore_patterns", JSON.stringify(patterns));
            }
```

- [ ] **Step 5: Update `renderResults` for ignored status**

In `renderResults()`, update the summary box to include ignored:

```javascript
            ${s.ignored > 0 ? `<div class="summary-item"><div class="summary-value" style="color:#6b7280;">${s.ignored}</div><div class="summary-label">Игнорировано</div></div>` : ""}
```

Update the results table row rendering:

```javascript
            resultsBody.innerHTML = data.results.map(r => {
                const statusClass = r.status === "found" ? "status-found" : r.status === "removed" ? "status-removed" : r.status === "ignored" ? "status-ignored" : "status-not-found";
                let statusText;
                if (r.status === "found") statusText = "Found";
                else if (r.status === "removed") statusText = "Removed";
                else if (r.status === "ignored") statusText = "Ignored";
                else statusText = "Not found";
                const urlHtml = r.repository_url
                    ? `<a href="${escapeHtml(r.repository_url)}" target="_blank">${escapeHtml(r.repository_url)}</a>`
                    : "&mdash;";
                const nameCell = r.name ? `<td>${escapeHtml(r.name)}</td>` : "";
                const versionCell = r.version ? `<td>${escapeHtml(r.version)}</td>` : "";
                return `<tr>
                    <td><code>${escapeHtml(r.purl)}</code></td>
                    <td class="${statusClass}">${statusText}</td>
                    <td class="repo-url-cell">${urlHtml}</td>
                    <td>${escapeHtml(r.found_by || "")}</td>
                    <td>${escapeHtml(r.resolver || "")}</td>
                    ${nameCell ? `<td>${escapeHtml(r.name)}</td>` : ""}
                    ${versionCell ? `<td>${escapeHtml(r.version)}</td>` : ""}
                </tr>`;
            }).join("");
```

Update the table `<thead>` to include name/version columns:

```html
                    <tr>
                        <th>PURL</th>
                        <th>Статус</th>
                        <th>Repository URL</th>
                        <th>Found by</th>
                        <th>Resolver</th>
                        <th>Name</th>
                        <th>Version</th>
                    </tr>
```

- [ ] **Step 6: Verify no syntax errors**

Open `http://localhost:8000/sbom-updater` in browser. The ignore patterns section should render below the checkboxes. Type a field and pattern, verify new row auto-appears. Save should work. Load should restore saved patterns.

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/templates/sbom.html
git commit -m "feat: add ignore patterns UI to SBOM Updater page"
```

---

### Task 8: Integration test with test SBOM

**Files:**
- Create: `tests/test_sbom_ignore_patterns.py`

- [ ] **Step 1: Write integration test**

```python
# tests/test_sbom_ignore_patterns.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from purl_resolver.sbom.collector import collect_components
from purl_resolver.sbom.reporter import build_report
from purl_resolver.sbom_enrichment import _component_matches_any_pattern


TEST_SBOM = Path(__file__).parent.parent / ".misc/addictional_materials/sbom_example_missed_references.json"


@pytest.fixture
def sbom_data():
    with open(TEST_SBOM, encoding="utf-8") as f:
        return json.load(f)


def test_ignore_patterns_filter_purl_contains_test(sbom_data):
    ignore_patterns = [
        {"field": "purl", "pattern": "test"},
        {"field": "group", "pattern": "test"},
    ]
    components = collect_components(sbom_data)

    # configure_interfaces-amd64 has purl containing "test"
    parent = next(c for c in components if c.name == "configure_interfaces-amd64")
    assert _component_matches_any_pattern(sbom_data, parent, ignore_patterns)

    # altgraph has no "test" in purl or group
    altgraph = next(c for c in components if c.name == "altgraph")
    assert not _component_matches_any_pattern(sbom_data, altgraph, ignore_patterns)

    # black has no "test" in purl or group
    black = next(c for c in components if c.name == "black")
    assert not _component_matches_any_pattern(sbom_data, black, ignore_patterns)


def test_ignore_patterns_independence_for_nested_components(sbom_data):
    """Parent being ignored must NOT cause children to be ignored."""
    ignore_patterns = [{"field": "purl", "pattern": "test"}]
    components = collect_components(sbom_data)

    for comp in components:
        comp_path_parents = comp.path[:-1] if comp.path[-1] == "components" else comp.path[:-2]
        pass

    matched = []
    for comp in components:
        if _component_matches_any_pattern(sbom_data, comp, ignore_patterns):
            matched.append(comp.name)

    # Only parent should match
    assert "configure_interfaces-amd64" in matched
    assert "altgraph" not in matched
    assert "black" not in matched
    assert "ptaf-task-manager" not in matched
    assert "certifi" not in matched
    assert "cffi" not in matched


def test_ignore_patterns_no_false_positives(sbom_data):
    """Components with unrelated field values should not match."""
    ignore_patterns = [{"field": "purl", "pattern": "nonexistent_value_xyz"}]
    components = collect_components(sbom_data)
    for comp in components:
        assert not _component_matches_any_pattern(sbom_data, comp, ignore_patterns)
```

- [ ] **Step 2: Run integration tests**

Run: `python -m pytest tests/test_sbom_ignore_patterns.py -v`
Expected: 3 PASSED

- [ ] **Step 3: Run full test suite to verify no regressions**

Run: `python -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 4: Commit**

```bash
git add tests/test_sbom_ignore_patterns.py
git commit -m "test: add integration tests for ignore patterns filtering"
```

---

### Task 9: Wire IgnorePatternsStore into main.py

**Files:**
- Modify: `src/purl_resolver/main.py`

- [ ] **Step 1: Read `main.py` to understand the pattern**

- [ ] **Step 2: Instantiate and attach `IgnorePatternsStore` to app state**

Add import:

```python
from .ignore_patterns_store import IgnorePatternsStore
```

In the lifespan (or startup), add:

```python
    ignore_patterns_store = IgnorePatternsStore()
    app.state.ignore_patterns_store = ignore_patterns_store
```

Wire it into the pipeline in the resolve endpoint. This is already done since the resolve endpoint creates a new pipeline each time — no changes needed if we pass `ignore_patterns_store` to the pipeline constructor.

Update `resolve.py` to pass `ignore_patterns_store` from app state to the pipeline:

```python
    pipeline = SbomEnrichmentPipeline(
        storage=request.app.state.storage,
        resolvers=request.app.state.resolvers,
        settings_store=getattr(request.app.state, "settings_store", None),
        ignore_patterns_store=getattr(request.app.state, "ignore_patterns_store", None),
    )
```

- [ ] **Step 3: Verify server starts correctly**

Run: `python -m pytest tests/ -v`
Expected: all tests PASSED

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/main.py src/purl_resolver/routes/resolve.py
git commit -m "feat: wire IgnorePatternsStore into app state and pipeline"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| `data/sbom_components_ignore_patterns.json` persistence | Task 1 |
| GET endpoint to load patterns | Task 5 |
| POST endpoint to save patterns | Task 5 |
| Auto-load patterns on page visit | Task 7 (step 3) |
| UI with key/contains/value rows, auto-add, "или" separator | Task 7 (step 2-3) |
| Save button | Task 7 (step 3) |
| `ignore_patterns` sent with resolve request | Task 7 (step 4) |
| Filtering step in pipeline (substring `contains`) | Task 3 |
| Independent component checking (children not auto-ignored) | Task 3 |
| `ignored` status in reporter | Task 4 |
| `ignored` in summary | Task 4 |
| Results table shows Ignored | Task 7 (step 5) |
| `sbom_example_missed_references.json` test | Task 8 |
| `configure_interfaces-amd64` ignored, `altgraph` not ignored | Task 8 |

No gaps found.