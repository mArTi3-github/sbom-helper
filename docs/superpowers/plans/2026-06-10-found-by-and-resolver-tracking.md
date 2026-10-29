# Found-by and Resolver Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show users how source code links were found (local DB vs resolver) and which resolver provided them, in both PURL Resolver and SBOM Updater UIs.

**Architecture:** A runtime-only `found_by` field is added to `ResolveResponse` — set to `"local_db"` for cache hits, `"resolver"` for fresh resolutions. The existing `resolver` field (persisted in DB) remains unchanged. `resolve_batch()` return type changes from `dict[str, str | None]` to `dict[str, ResolveResponse]` to propagate metadata through the SBOM pipeline.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Jinja2, pytest + pytest-asyncio

---

### Task 1: Add `found_by` field to `ResolveResponse`

**Files:**
- Modify: `src/purl_resolver/schemas.py:16-27`
- Test: `tests/test_api.py` (existing test implicitly covers new field)

- [ ] **Step 1: Add `found_by` field**

In `src/purl_resolver/schemas.py`, add `found_by: str = ""` after `resolver`:

```python
class ResolveResponse(BaseModel):
    purl: str
    repository_url: str | None = None
    repository_type: str | None = None
    repository_kind: str | None = None
    confidence: str | None = None
    evidence: list[str] = []
    warnings: list[str] = []
    version_reference: str | None = None
    resolver: str = ""
    found_by: str = ""
    resolved_at: str = ""
```

- [ ] **Step 2: Verify existing API tests still pass**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_api.py -v`
Expected: All tests PASS (new field defaults to `""`, existing assertions don't check it)

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/schemas.py
git commit -m "feat(schema): add found_by field to ResolveResponse"
```

---

### Task 2: Service layer — set `found_by` and change `resolve_batch` return type

**Files:**
- Modify: `src/purl_resolver/service.py:78-164`
- Test: `tests/test_service_validation.py`
- Test: `tests/test_resolve_batch.py`

- [ ] **Step 1: Write tests for `found_by` in `resolve_purl` cache-hit path**

In `tests/test_service_validation.py`, add a test class after existing imports. The resolver must have `name="fake"` to match what `FakeResolver` provides:

```python
class TestFoundBy:
    @pytest.mark.asyncio
    async def test_found_by_local_db_when_cached(self, mock_storage, mock_settings_store, resolver):
        cached = ResolveResponse(
            purl="pkg:pypi/requests",
            repository_url="https://github.com/psf/requests",
            resolver="purl2repo",
            resolved_at=datetime.now().isoformat(),
        )
        mock_storage.lookup = AsyncMock(return_value=cached)
        with patch("purl_resolver.service._validate_cached_url", new_callable=AsyncMock, return_value=cached):
            result = await resolve_purl(
                "pkg:pypi/requests@2.31.0", mock_storage, [resolver], mock_settings_store
            )
        assert result.response is not None
        assert result.response.found_by == "local_db"
        assert result.response.resolver == "purl2repo"

    @pytest.mark.asyncio
    async def test_found_by_resolver_when_fresh(self, mock_storage, mock_settings_store, resolver):
        mock_storage.lookup = AsyncMock(return_value=None)
        resolver.name = "fake_resolver"
        result = await resolve_purl(
            "pkg:pypi/requests@2.31.0", mock_storage, [resolver], mock_settings_store
        )
        assert result.response is not None
        assert result.response.found_by == "resolver"
        assert result.response.resolver == "fake_resolver"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_service_validation.py::TestFoundBy -v`
Expected: FAIL — `found_by` not set on response

- [ ] **Step 3: Set `found_by` in `resolve_purl`**

In `src/purl_resolver/service.py`, two changes:

**Cache hit path** (around line 97, after `_validate_cached_url` returns):
```python
        if cached is not None:
            cached.found_by = "local_db"
            return ResolveResult.ok(cached)
```

**Fresh resolver path** (around line 126, alongside `resolver=r.name`):
```python
        response = ResolveResponse(
            ...
            resolver=r.name,
            found_by="resolver",
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_service_validation.py::TestFoundBy -v`
Expected: PASS

- [ ] **Step 5: Update `resolve_batch` return type and tests**

In `src/purl_resolver/service.py`, change `resolve_batch`:

```python
async def resolve_batch(
    purls: list[str],
    storage: Storage,
    resolvers: list[Resolver],
    settings_store: SettingsStore | None = None,
    resolver: str = "",
) -> dict[str, ResolveResponse]:
    semaphore = asyncio.Semaphore(_BATCH_SEMAPHORE_LIMIT)

    async def _resolve_one(original: str) -> tuple[str, ResolveResponse | None]:
        async with semaphore:
            result = await resolve_purl(original, storage, resolvers, settings_store=settings_store, resolver=resolver)
            key = safe_normalize(original)
            if result.response and result.response.repository_url:
                return (key, result.response)
            return (key, None)

    tasks = [_resolve_one(p) for p in purls]
    results = await asyncio.gather(*tasks)
    return {k: v for k, v in results if v is not None}

async def store_preexisting_references(
    components: list[SbomComponent],
    storage: Storage,
    resolver: str = "",
) -> None:
    for comp in components:
        if comp.needs_enrichment:
            continue
        for ref in comp.existing_references:
            if ref.get("type") == "vcs" and ref.get("url"):
                purl_key = safe_normalize(comp.purl)
                try:
                    existing = await storage.lookup(purl_key)
                except Exception:
                    existing = None
                if existing is None:
                    await storage.store(ResolveResponse(
                        purl=purl_key,
                        repository_url=ref["url"],
                        evidence=["from SBOM externalReferences"],
                        resolver=resolver,
                    ))
                break
```

- [ ] **Step 6: Update `test_resolve_batch.py` tests for new return type**

In `tests/test_resolve_batch.py`, update existing tests. The return type changes from `dict[str, str | None]` to `dict[str, ResolveResponse]`, so assertions need to access `.repository_url`:

```python
class TestResolveBatch:

    @pytest.mark.asyncio
    async def test_resolves_multiple_purls(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                repository_type="github",
                repository_kind="source_code",
                confidence="high",
            )
        )
        purls = [
            "pkg:pypi/requests@2.31.0",
            "pkg:npm/express@4.17.1",
            "pkg:pypi/flask@3.0.0",
        ]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 3
        for key, resp in result.items():
            assert resp.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_skips_purls_with_no_repository_url(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url=None,
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_uses_normalized_keys(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0", "pkg:pypi/requests@3.0.0"]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 1
        assert "pkg:pypi/requests" in result

    @pytest.mark.asyncio
    async def test_empty_purl_list(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver()
        result = await resolve_batch([], storage, [resolver])
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_stores_resolved_results_in_storage(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                confidence="high",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        await resolve_batch(purls, storage, [resolver])
        cached = await storage.lookup("pkg:pypi/requests")
        assert cached is not None
        assert cached.repository_url == "https://github.com/psf/requests"

    @pytest.mark.asyncio
    async def test_resolved_entries_have_found_by_and_resolver(self, storage: InMemoryCache) -> None:
        resolver = FakeResolver(
            resolution=Resolution(
                purl="pkg:pypi/requests@2.31.0",
                repository_url="https://github.com/psf/requests",
                confidence="high",
            )
        )
        purls = ["pkg:pypi/requests@2.31.0"]
        result = await resolve_batch(purls, storage, [resolver])
        assert len(result) == 1
        resp = result["pkg:pypi/requests"]
        assert resp.found_by == "resolver"
        assert resp.resolver == "fake"
```

- [ ] **Step 7: Run batch tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_resolve_batch.py -v`
Expected: All tests PASS (6 tests, including new `test_resolved_entries_have_found_by_and_resolver`)

- [ ] **Step 8: Add API-level test for `found_by` in `test_api.py`**

Add to `TestResolve` class in `tests/test_api.py`:

```python
    def test_resolve_response_includes_found_by(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "found_by" in data
        assert data["found_by"] == "resolver"

    def test_cached_response_includes_found_by_local_db(self, client: TestClient) -> None:
        first = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert first.status_code == 200
        # Cache the first result by storing it
        cached_data = first.json()
        # Second request hits the in-memory cache
        second = client.post(
            "/api/v1/resolve",
            json={"purl": "pkg:pypi/requests@2.31.0"},
        )
        assert second.status_code == 200
        data = second.json()
        assert data["found_by"] == "local_db"
        assert data["resolver"] == cached_data["resolver"]
```

- [ ] **Step 9: Run all tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_api.py tests/test_resolve_batch.py tests/test_service_validation.py -v`
Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add src/purl_resolver/service.py tests/test_resolve_batch.py tests/test_service_validation.py tests/test_api.py
git commit -m "feat(service): add found_by tracking and change resolve_batch return type"
```

---

### Task 3: SBOM pipeline — propagate `found_by` and `resolver` through reporter

**Files:**
- Modify: `src/purl_resolver/sbom_enrichment.py:62-71`
- Modify: `src/purl_resolver/sbom/reporter.py:7-56`
- Test: `tests/test_sbom_reporter.py`
- Test: `tests/test_sbom_enricher.py`

- [ ] **Step 1: Write tests for new reporter fields**

In `tests/test_sbom_reporter.py`, add to `TestBuildReport`:

```python
    def test_found_result_includes_found_by_and_resolver(self) -> None:
        from purl_resolver.schemas import ResolveResponse
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved = {
            "pkg:pypi/a": ResolveResponse(
                purl="pkg:pypi/a",
                repository_url="https://example.com/a",
                found_by="resolver",
                resolver="ecosyste.ms",
            )
        }
        report = build_report(components, resolved, skipped=0)
        item = report["results"][0]
        assert item["found_by"] == "resolver"
        assert item["resolver"] == "ecosyste.ms"

    def test_not_found_result_has_empty_found_by(self) -> None:
        from purl_resolver.schemas import ResolveResponse
        components = [
            SbomComponent(name="a", version="1", purl="pkg:pypi/a@1", path=("components", 0), needs_enrichment=True),
        ]
        resolved: dict[str, ResolveResponse] = {}
        report = build_report(components, resolved, skipped=0)
        item = report["results"][0]
        assert item["found_by"] == ""
        assert item["resolver"] == ""
```

- [ ] **Step 2: Run reporter tests to verify they fail**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_sbom_reporter.py::TestBuildReport -v`
Expected: Tests fail because `build_report` still expects `dict[str, str]`

- [ ] **Step 3: Update `build_report` in `reporter.py`**

In `src/purl_resolver/sbom/reporter.py`, change the signature and result construction:

```python
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

    for comp in components:
        if not comp.needs_enrichment:
            continue
        key = safe_normalize(comp.purl)
        if key in seen:
            continue
        seen.add(key)
        if key in removed_keys:
            continue
        resp = resolved.get(key)
        repo_url = resp.repository_url if resp else None
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
        },
        "results": results,
    }
```

Add import at top of file:
```python
from ..schemas import ResolveResponse
```

- [ ] **Step 4: Run reporter tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_sbom_reporter.py -v`
Expected: All PASS (including new tests)

- [ ] **Step 5: Update `sbom_enrichment.py` to extract URLs for `enrich_sbom`**

In `src/purl_resolver/sbom_enrichment.py`, change the `process` method:

```python
        resolved = await resolve_batch(
            unique_purls,
            self._storage,
            self._resolvers,
            settings_store=self._settings_store,
            resolver="import-sbom",
        )
        # Extract URLs for enrich_sbom (its interface stays dict[str, str])
        resolved_urls: dict[str, str] = {
            k: v.repository_url for k, v in resolved.items() if v is not None
        }
        await store_preexisting_references(
            components, self._storage, resolver="import-sbom"
        )

        removed: list[dict] = []
        enrich_sbom(sbom_data, components, resolved_urls)
```

- [ ] **Step 6: Update sbom enricher test that directly calls `build_report`**

In `tests/test_sbom_enricher.py`, update the `test_build_report_includes_removed` method. Change `resolved` from a `dict[str, str]` to `dict[str, ResolveResponse]`:

```python
    def test_build_report_includes_removed(self) -> None:
        from purl_resolver.sbom.reporter import build_report
        from purl_resolver.schemas import ResolveResponse
        sbom = {
            "version": 1,
            "metadata": {"timestamp": "2024-01-01T00:00:00"},
            "components": [
                {"type": "library", "name": "a", "version": "1.0", "purl": "pkg:pypi/a@1.0"},
            ],
        }
        components = collect_components(sbom)
        resolved = {
            "pkg:pypi/a": ResolveResponse(
                purl="pkg:pypi/a",
                repository_url="https://github.com/example/a",
                found_by="resolver",
                resolver="fake",
            ),
        }
        removed = [{"purl": "pkg:pypi/b@2", "name": "b", "version": "2"}]
        report = build_report(components, resolved, skipped=0, removed=removed)
        assert report["summary"]["removed"] == 1
        assert any(r["status"] == "removed" for r in report["results"])
```

- [ ] **Step 7: Run enricher tests**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest tests/test_sbom_enricher.py -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add src/purl_resolver/sbom/reporter.py src/purl_resolver/sbom_enrichment.py tests/test_sbom_reporter.py
git add tests/test_sbom_enricher.py tests/test_sbom_integration.py
git commit -m "feat(sbom): propagate found_by and resolver through SBOM pipeline"
```

---

### Task 4: Frontend — display `found_by` and `resolver` in PURL Resolver page

**Files:**
- Modify: `src/purl_resolver/templates/index.html:144-181`

- [ ] **Step 1: Update `renderSuccess()` to show Found by and Resolver**

In `src/purl_resolver/templates/index.html`, inside the `detailsHtml` template string, add after the version_reference block (around line 165):

```javascript
                            ${data.version_reference ? "<dt>Version Reference</dt><dd><a href=\"" + escapeHtml(data.version_reference) + "\" target=\"_blank\">" + escapeHtml(data.version_reference) + "</a></dd>" : ""}
                            ${data.found_by ? "<dt>Found by</dt><dd>" + escapeHtml(data.found_by) + "</dd>" : ""}
                            ${data.resolver ? "<dt>Resolver</dt><dd>" + escapeHtml(data.resolver) + "</dd>" : ""}
```

Also update the condition for showing the details toggle (line 148) to include `found_by`:

```javascript
            if (data.evidence?.length || data.warnings?.length || data.repository_type || data.repository_kind || data.version_reference || data.found_by || data.resolver) {
```

- [ ] **Step 2: Verify the page loads and renders correctly**

Start the server and test manually (or rely on existing functional tests).

- [ ] **Step 3: Commit**

```bash
git add src/purl_resolver/templates/index.html
git commit -m "feat(ui): show found_by and resolver in PURL resolver details"
```

---

### Task 5: Frontend — add Found by and Resolver columns to SBOM Updater table

**Files:**
- Modify: `src/purl_resolver/templates/sbom.html:110-117, 238-249`

- [ ] **Step 1: Add columns to table header**

In `src/purl_resolver/templates/sbom.html`, change the `<thead>`:

```html
            <table>
                <thead>
                    <tr>
                        <th>PURL</th>
                        <th>Статус</th>
                        <th>Repository URL</th>
                        <th>Found by</th>
                        <th>Resolver</th>
                    </tr>
                </thead>
```

- [ ] **Step 2: Add cells to results rows**

In `src/purl_resolver/templates/sbom.html`, change the `resultsBody.innerHTML` map:

```javascript
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
                    <td>${escapeHtml(r.found_by || "")}</td>
                    <td>${escapeHtml(r.resolver || "")}</td>
                </tr>`;
            }).join("");
```

- [ ] **Step 3: Verify by running full test suite**

Run: `cd /home/administrator/Desktop/projects/sbom-helper && .venv/bin/python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/purl_resolver/templates/sbom.html
git commit -m "feat(ui): add found_by and resolver columns to SBOM updater table"
```

---

### Task 6: Verify resolver self-identification

**Files:**
- Inspect: `src/purl_resolver/resolver/purl2repo.py`
- Inspect: `src/purl_resolver/resolver/ecosystems.py`
- Inspect: `src/purl_resolver/resolver/librariesio.py`

- [ ] **Step 1: Verify each resolver correctly reports its name**

Check that each resolver's `name` property matches the expected value:

| Resolver | `name` returns | Used in DB |
|---|---|---|
| `purl2repo.py` | `"purl2repo"` | yes |
| `ecosystems.py` | `"ecosyste.ms"` | yes |
| `librariesio.py` | `"libraries.io"` | yes |

No changes needed — resolvers already correctly self-identify. The `service.py` already uses `resolver=r.name` when building the response.

- [ ] **Step 2: Commit (skip if no changes)**

No file changes needed for this task. Close it.