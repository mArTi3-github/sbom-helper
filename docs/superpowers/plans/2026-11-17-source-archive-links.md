# Source Archive Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mode to `POST /api/v1/resolve/batch` and the PURL Resolver UI that finds a version-specific GitHub source archive URL, reports whether it is exact or near, and caches the result (including negative results) in PostgreSQL.

**Architecture:** A new `source_archive/` package holds pure version/tag matching, `git ls-remote` tag retrieval, GitHub archive URL construction, and `SourceArchiveService`. The service is called by the existing resolve route after repository resolution; it reads and writes a new `purl_source_archives` table through a dedicated storage interface. Matching is deterministic; LLM is intentionally not used in this version.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, asyncpg, httpx, pytest/pytest-asyncio, Vue 3 + TypeScript, Vitest, Bash.

**Spec:** `docs/superpowers/specs/2026-11-17-source-archive-links-design.md`

## Global Constraints

- Python runs from `.venv`: `.venv/bin/python -m pytest -q`. If only e2e tests fail due to network, rerun with `SKIP_E2E=1`.
- Frontend checks: `npm --prefix frontend run test`, `npm --prefix frontend run build`.
- New table name: `purl_source_archives`; cache key: canonical PURL including version, without qualifiers/subpath.
- `match_type` values: `exact`, `near`, `repository_only`, `not_found`; API-only value `no_version`.
- `reason` values, precedence order: `no_version`, `non_numeric_version`, `no_repository`, `unsupported_host`, `git_error`, `archive_check_failed`, `no_matching_tag`.
- Archive format is always `.tar.gz`; only `github.com` / `www.github.com` are supported.
- Settings: `source_archive_timeout` default `30.0`, range 1–300; `source_archive_concurrency` default `5`, range 1–50.
- Do not use an LLM in this version; do not add LLM settings or prompts.
- Do not change `resolved_purls` key semantics (versionless) or its four columns.
- No code comments unless the surrounding file already uses them.
- Commit after each task with a meaningful message. Do not push.

## Review Focus

1. **PURL without version or with non-numeric version** (`@main`, `@latest`) must return `no_version` / `non_numeric_version` without crashing or calling git, even when `find_source_archive=true`.
2. **Unusual tag names and large tag lists** (`rel_23_8_16_40`, `v1.2.3-rc4`, tags containing `/`, thousands of tags) must classify correctly and produce a properly percent-encoded archive URL.
3. **Repository URL changes between requests** (redirect update, DB edit) must not serve an archive URL built from the old repository; the row is refreshed.
4. **GitHub archive HEAD redirects** to `codeload.github.com` must be followed; a redirect must count as success, not failure.
5. **PostgreSQL unavailable** (in-memory fallback) must not break the feature: lookups still work for the process lifetime and storage failures never turn a successful archive result into an HTTP 500.

---

## File Structure

**Create:**
- `src/purl_resolver/source_archive/__init__.py` — package marker.
- `src/purl_resolver/source_archive/matching.py` — version parsing, exact/near classification, tie-breaking.
- `src/purl_resolver/source_archive/git_tags.py` — `git ls-remote --tags` parsing and execution.
- `src/purl_resolver/source_archive/github.py` — GitHub repo parsing, archive URL construction, HEAD check.
- `src/purl_resolver/source_archive/service.py` — `SourceArchiveService` orchestration and caching.
- `src/purl_resolver/storage/source_archive.py` — `SourceArchiveRow`, `SourceArchiveStorage` ABC.
- `src/purl_resolver/storage/postgres_source_archive.py` — PostgreSQL implementation.
- `src/purl_resolver/storage/inmemory_source_archive.py` — in-memory fallback.
- `tests/test_source_archive_matching.py`
- `tests/test_source_archive_git_tags.py`
- `tests/test_source_archive_github.py`
- `tests/test_source_archive_storage.py`
- `tests/test_source_archive_service.py`
- `tests/test_source_archive_api.py`

**Modify:**
- `src/purl_resolver/storage/schema.sql` — add table.
- `src/purl_resolver/main.py` — construct archive storage and service.
- `src/purl_resolver/schemas.py` — request flags and response fields.
- `src/purl_resolver/routes/resolve.py` — call archive service.
- `src/purl_resolver/settings_store.py` — two new settings.
- `src/purl_resolver/routes/settings.py` — GET/PATCH/validation for them.
- `tests/test_api.py` — settings fields and service wiring.
- `frontend/src/types/api.ts`, `frontend/src/api/purl.ts` — flags and fields.
- `frontend/src/views/PurlResolver.vue`, `frontend/src/views/PurlResolver.test.ts` — mode, columns, badges.
- `frontend/src/stores/useSettingsStore.ts`, `frontend/src/views/Settings.vue`, `frontend/src/views/Settings.test.ts` — settings fields.
- `frontend/src/i18n/locales/ru.json`, `frontend/src/i18n/locales/en.json` — strings.
- `scripts/db_backup.sh`, `scripts/db_restore.sh`, `tests/test_db_backup_scripts.py`.
- `frontend/src/components/db/DbBackupHelp.vue`, `README.md`.
- `specs/domains/purl-resolution.md`, `specs/contracts/api-contract.md`, `specs/domains/web-ui.md`, `specs/architecture/layers.md`, `specs/INDEX.md`; create `specs/decisions/0009-source-archive-links.md`.

---

### Task 1: Version and tag matching primitives

**Files:**
- Create: `src/purl_resolver/source_archive/__init__.py`
- Create: `src/purl_resolver/source_archive/matching.py`
- Test: `tests/test_source_archive_matching.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) TagInfo(name: str, commit_sha: str | None = None)`
  - `@dataclass(frozen=True) VersionParts(numbers: tuple[int, ...], suffix: str)`
  - `@dataclass(frozen=True) TagMatch(tag: TagInfo, match_type: Literal["exact", "near"], matched_version: str)`
  - `parse_version(text: str) -> VersionParts | None`
  - `find_exact(tags: Sequence[TagInfo], version: VersionParts) -> list[TagMatch]` (sorted by priority)
  - `find_near(tags: Sequence[TagInfo], version: VersionParts) -> TagMatch | None`
  - `pick_nearer(version: VersionParts, first: TagMatch, second: TagMatch) -> TagMatch`

- [ ] **Step 1: Write failing tests**

Create `tests/test_source_archive_matching.py`:

```python
from purl_resolver.source_archive.matching import (
    TagInfo,
    find_exact,
    find_near,
    parse_version,
    pick_nearer,
)


def tags(*names: str) -> list[TagInfo]:
    return [TagInfo(name=n, commit_sha=f"sha-{n}") for n in names]


def test_parse_version_splits_numeric_chain_and_suffix() -> None:
    assert parse_version("23.8.16.40").numbers == (23, 8, 16, 40)
    assert parse_version("2.0.0-rc1").suffix == "rc1"
    assert parse_version("main") is None


def test_find_exact_accepts_tag_prefix_and_suffix() -> None:
    version = parse_version("23.8.16.40")
    matches = find_exact(tags("v23.8.16.40-lts"), version)
    assert matches[0].tag.name == "v23.8.16.40-lts"
    assert matches[0].match_type == "exact"
    assert matches[0].matched_version == "23.8.16.40"


def test_find_exact_handles_underscore_separated_tags() -> None:
    assert find_exact(tags("rel_23_8_16_40"), parse_version("23.8.16.40"))[0].tag.name == "rel_23_8_16_40"


def test_find_exact_pads_missing_components() -> None:
    assert find_exact(tags("v1.2.0"), parse_version("1.2"))[0].match_type == "exact"


def test_find_exact_requires_matching_prerelease_suffix() -> None:
    assert find_exact(tags("v2.0.0"), parse_version("2.0.0-rc1")) == []


def test_find_exact_priority_prefers_non_prerelease_then_shorter() -> None:
    matches = find_exact(tags("v1.2.3-rc1", "v1.2.3-lts", "1.2.3"), parse_version("1.2.3"))
    assert [m.tag.name for m in matches] == ["1.2.3", "v1.2.3-lts", "v1.2.3-rc1"]


def test_find_near_prefers_lower_then_higher_in_same_major_minor() -> None:
    version = parse_version("23.8.16.40")
    assert find_near(tags("v23.8.16.39", "v23.8.16.41"), version).tag.name == "v23.8.16.39"
    assert find_near(tags("v23.8.16.41"), version).tag.name == "v23.8.16.41"


def test_find_near_rejects_other_major_minor() -> None:
    assert find_near(tags("v24.1.0", "v23.9.1"), parse_version("23.8.16.40")) is None


def test_find_near_includes_equal_numbers_with_suffix_mismatch() -> None:
    match = find_near(tags("v2.5.0", "v2.4.9"), parse_version("2.5.0-rc1"))
    assert match.tag.name == "v2.5.0"
    assert match.match_type == "near"


def test_pick_nearer_uses_distance_priority() -> None:
    version = parse_version("2.5.0")
    lower = find_near(tags("v2.4.9"), version)
    higher = find_near(tags("v2.5.1"), version)
    assert pick_nearer(version, lower, higher).tag.name == "v2.4.9"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_matching.py -q`
Expected: FAIL with `ModuleNotFoundError` or missing names.

- [ ] **Step 3: Implement the module**

Implement `matching.py` with:
- numeric-chain extraction: split into digit/non-digit runs; choose the longest chain of digit runs joined only by separators without letters (`. - _ / +`), earliest chain on ties;
- `suffix` normalized to lowercase alphanumerics only;
- prerelease markers `rc`, `alpha`, `beta`, `pre`, `dev`, `snapshot`, `nightly` detected at the start of `suffix`;
- exact comparison with zero padding; suffix must match only when the target has a suffix;
- exact ordering: non-prerelease first, then shorter name, then lexicographic;
- near only within padded `major.minor`; skip prerelease tags unless the target is prerelease; rank numerically equal first, then greatest below, then smallest above;
- `pick_nearer` applies the same ranking to two `near` matches.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_matching.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/source_archive tests/test_source_archive_matching.py
git commit -m "feat(source-archive): add version and tag matching primitives"
```

---

### Task 2: `git ls-remote --tags` retrieval

**Files:**
- Create: `src/purl_resolver/source_archive/git_tags.py`
- Test: `tests/test_source_archive_git_tags.py`

**Interfaces:**
- Consumes: `TagInfo` from Task 1.
- Produces:
  - `class GitTagsError(Exception)`
  - `parse_ls_remote(output: str) -> list[TagInfo]`
  - `async def fetch_tags(repository_url: str, timeout: float) -> list[TagInfo]`

- [ ] **Step 1: Write failing tests**

```python
import asyncio
import os
import stat

import pytest

from purl_resolver.source_archive.git_tags import (
    GitTagsError,
    fetch_tags,
    parse_ls_remote,
)


def test_parse_lightweight_and_annotated_tags() -> None:
    output = (
        "aaa\trefs/tags/v1.0.0\n"
        "bbb\trefs/tags/v1.1.0\n"
        "ccc\trefs/tags/v1.1.0^{}\n"
        "ddd\trefs/heads/main\n"
    )
    parsed = {t.name: t.commit_sha for t in parse_ls_remote(output)}
    assert parsed == {"v1.0.0": "aaa", "v1.1.0": "ccc"}


@pytest.mark.asyncio
async def test_fetch_tags_rejects_non_http_url() -> None:
    with pytest.raises(GitTagsError):
        await fetch_tags("file:///tmp/repo", timeout=1)


@pytest.mark.asyncio
async def test_fetch_tags_kills_process_on_timeout(tmp_path) -> None:
    fake_git = tmp_path / "git"
    fake_git.write_text("#!/bin/sh\nsleep 10\n")
    fake_git.chmod(fake_git.stat().st_mode | stat.S_IEXEC)
    with pytest.MonkeyPatch.context() as mp:
        mp.setenv("PATH", f"{tmp_path}:{os.environ['PATH']}")
        with pytest.raises(GitTagsError):
            await asyncio.wait_for(
                fetch_tags("https://github.com/example/repo", timeout=0.2),
                timeout=2,
            )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_git_tags.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `git_tags.py`**

- `parse_ls_remote`: parse `<sha>\trefs/tags/<name>`; strip `^{}` and attach the peeled SHA as `commit_sha`, overriding the tag-object SHA; skip non-tag and malformed lines.
- `fetch_tags`: require `http`/`https` with a hostname; run `git ls-remote --tags <url>` via `asyncio.create_subprocess_exec` with `GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/true`; enforce `timeout` and kill the process on expiry; raise `GitTagsError` on non-zero exit, timeout, output larger than 5 MB, or more than 50 000 tags.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_git_tags.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/source_archive/git_tags.py tests/test_source_archive_git_tags.py
git commit -m "feat(source-archive): fetch tags via git ls-remote"
```

---

### Task 3: GitHub archive URLs and HEAD check

**Files:**
- Create: `src/purl_resolver/source_archive/github.py`
- Test: `tests/test_source_archive_github.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) GitHubRepo(owner: str, name: str)`
  - `parse_github_repository(url: str) -> GitHubRepo | None`
  - `tag_archive_url(repo: GitHubRepo, tag: str) -> str`
  - `commit_archive_url(repo: GitHubRepo, sha: str) -> str`
  - `async def check_archive_url(url: str, timeout: float, client: httpx.AsyncClient | None = None) -> bool`

- [ ] **Step 1: Write failing tests**

```python
import httpx
import pytest

from purl_resolver.source_archive.github import (
    GitHubRepo,
    check_archive_url,
    commit_archive_url,
    parse_github_repository,
    tag_archive_url,
)


def test_parse_github_repository_variants() -> None:
    assert parse_github_repository("https://github.com/ClickHouse/ClickHouse.git") == GitHubRepo("ClickHouse", "ClickHouse")
    assert parse_github_repository("https://www.github.com/psf/requests/") == GitHubRepo("psf", "requests")


def test_parse_github_repository_rejects_other_hosts_and_extra_paths() -> None:
    assert parse_github_repository("https://gitlab.com/a/b") is None
    assert parse_github_repository("https://github.com/a/b/tree/main") is None


def test_archive_urls() -> None:
    repo = GitHubRepo("ClickHouse", "ClickHouse")
    assert tag_archive_url(repo, "v23.8.16.40-lts") == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/v23.8.16.40-lts.tar.gz"
    )
    assert tag_archive_url(repo, "release/1.2.3") == (
        "https://github.com/ClickHouse/ClickHouse/archive/refs/tags/release/1.2.3.tar.gz"
    )
    assert commit_archive_url(repo, "e143a9039ba36ad0c25f2ed85503f36e88f61063") == (
        "https://github.com/ClickHouse/ClickHouse/archive/e143a9039ba36ad0c25f2ed85503f36e88f61063.tar.gz"
    )


@pytest.mark.asyncio
async def test_check_archive_url_follows_redirect() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "github.com":
            return httpx.Response(302, headers={"location": "https://codeload.github.com/x/y/tar.gz/abc"})
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as client:
        assert await check_archive_url("https://github.com/x/y/archive/abc.tar.gz", 5, client=client)


@pytest.mark.asyncio
async def test_check_archive_url_returns_false_on_http_error() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    async with httpx.AsyncClient(transport=transport) as client:
        assert not await check_archive_url("https://github.com/x/y/archive/abc.tar.gz", 5, client=client)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_github.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `github.py`**

- Accept only host `github.com` or `www.github.com`, path exactly `/{owner}/{repo}` after stripping one trailing `/` and one trailing `.git`; validate owner/repo with `^[A-Za-z0-9_.-]+$`.
- URL-encode the tag with `urllib.parse.quote(tag, safe="/")`; SHA must be exactly 40 hex characters (raise `ValueError` otherwise).
- `check_archive_url` uses the provided client or creates one with `follow_redirects=True`, performs HEAD, returns `status_code < 400`, and returns `False` on `httpx.HTTPError`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_github.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/source_archive/github.py tests/test_source_archive_github.py
git commit -m "feat(source-archive): build and verify GitHub archive URLs"
```

---

### Task 4: Archive storage and schema

**Files:**
- Create: `src/purl_resolver/storage/source_archive.py`
- Create: `src/purl_resolver/storage/inmemory_source_archive.py`
- Create: `src/purl_resolver/storage/postgres_source_archive.py`
- Modify: `src/purl_resolver/storage/schema.sql`
- Test: `tests/test_source_archive_storage.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) SourceArchiveRow` with fields `purl`, `version`, `match_type`, `reason`, `archive_url`, `archive_url_commit`, `matched_ref`, `matched_ref_type`, `matched_version`, `repository_url`, `resolver`, `resolved_at`
  - `class SourceArchiveStorage(ABC)` with `async lookup_archive(purl: str) -> SourceArchiveRow | None` and `async store_archive(row: SourceArchiveRow) -> None`
  - `InMemorySourceArchiveStorage`
  - `PostgresSourceArchiveStorage(pool: asyncpg.Pool)`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from purl_resolver.storage.inmemory_source_archive import InMemorySourceArchiveStorage
from purl_resolver.storage.source_archive import SourceArchiveRow


def row(purl: str = "pkg:github/a/b@1.2.3", match_type: str = "exact") -> SourceArchiveRow:
    return SourceArchiveRow(
        purl=purl,
        version="1.2.3",
        match_type=match_type,
        archive_url="https://github.com/a/b/archive/refs/tags/v1.2.3.tar.gz",
        matched_ref="v1.2.3",
        matched_ref_type="tag",
        matched_version="1.2.3",
        repository_url="https://github.com/a/b",
        resolver="git-tags",
        resolved_at="2026-11-17T12:00:00+00:00",
    )


@pytest.mark.asyncio
async def test_store_and_lookup_roundtrip() -> None:
    storage = InMemorySourceArchiveStorage()
    await storage.store_archive(row())
    assert await storage.lookup_archive("pkg:github/a/b@1.2.3") == row()


@pytest.mark.asyncio
async def test_lookup_miss_returns_none() -> None:
    assert await InMemorySourceArchiveStorage().lookup_archive("pkg:github/a/b@9.9.9") is None


@pytest.mark.asyncio
async def test_store_overwrites_existing_purl() -> None:
    storage = InMemorySourceArchiveStorage()
    await storage.store_archive(row(match_type="not_found"))
    await storage.store_archive(row(match_type="exact"))
    stored = await storage.lookup_archive("pkg:github/a/b@1.2.3")
    assert stored.match_type == "exact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_storage.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement storage and schema**

- Add the `purl_source_archives` table and `idx_purl_source_archives_match_type` index exactly as specified in the design doc, section 6.2.
- `PostgresSourceArchiveStorage.lookup_archive`: `SELECT * ... WHERE purl = $1`, map to the dataclass, `str(resolved_at)`.
- `PostgresSourceArchiveStorage.store_archive`: `INSERT ... VALUES (...) ON CONFLICT (purl) DO UPDATE SET` all mutable columns and `resolved_at = EXCLUDED.resolved_at`.
- `InMemorySourceArchiveStorage`: dict keyed by `purl`.
- SQL behavior is exercised by the docker-backed script tests in Tasks 10–11.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_storage.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/storage tests/test_source_archive_storage.py
git commit -m "feat(source-archive): add archive cache storage"
```

---

### Task 5: Settings for timeout and concurrency

**Files:**
- Modify: `src/purl_resolver/settings_store.py`
- Modify: `src/purl_resolver/routes/settings.py`
- Modify: `tests/test_api.py`

**Interfaces:**
- Produces in `AppSettings`:
  - `source_archive_timeout: float = 30.0` (`ge=1, le=300`)
  - `source_archive_concurrency: int = 5` (`ge=1, le=50`)
- Produces in `SettingsUpdate` the same two optional fields with the same bounds; both appear in `GET` and `PATCH` responses.

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
class TestSourceArchiveSettings:
    def test_get_settings_includes_source_archive_fields(self, client: TestClient) -> None:
        data = client.get("/api/v1/settings").json()
        assert data["source_archive_timeout"] == 30.0
        assert data["source_archive_concurrency"] == 5

    def test_patch_source_archive_settings(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "source_archive_timeout": 45.5,
            "source_archive_concurrency": 8,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["source_archive_timeout"] == 45.5
        assert data["source_archive_concurrency"] == 8

    def test_patch_source_archive_settings_bounds(self, client: TestClient) -> None:
        assert client.patch("/api/v1/settings", json={"source_archive_timeout": 0}).status_code == 422
        assert client.patch("/api/v1/settings", json={"source_archive_timeout": 301}).status_code == 422
        assert client.patch("/api/v1/settings", json={"source_archive_concurrency": 0}).status_code == 422
        assert client.patch("/api/v1/settings", json={"source_archive_concurrency": 51}).status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py::TestSourceArchiveSettings -q`
Expected: FAIL with `KeyError` / 422 on valid values.

- [ ] **Step 3: Implement settings**

Add the fields to `AppSettings` and `SettingsUpdate`, and to both JSON response dicts in `routes/settings.py`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api.py::TestSourceArchiveSettings -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py src/purl_resolver/routes/settings.py tests/test_api.py
git commit -m "feat(source-archive): add timeout and concurrency settings"
```

---

### Task 6: `SourceArchiveService` and cache

**Files:**
- Create: `src/purl_resolver/source_archive/service.py`
- Test: `tests/test_source_archive_service.py`

**Interfaces:**
- Consumes: Tasks 1–5; `normalize_with_version` from `purl_utils` (add it in this task).
- Produces:
  - `MatchType = Literal["exact", "near", "repository_only", "not_found", "no_version"]`
  - `@dataclass(frozen=True) SourceArchiveResult` with fields `purl`, `match_type`, `reason`, `archive_url`, `archive_url_commit`, `matched_ref`, `matched_ref_type`, `matched_version`, `repository_url`, `resolver`, `cached`, `resolved_at`, `warnings`
  - `class SourceArchiveService(storage, settings_store, tag_fetcher=fetch_tags, url_checker=check_archive_url)`
  - `async lookup(purl: str, repository_url: str | None, force_refresh: bool = False) -> SourceArchiveResult`
  - `async enrich_many(purls: list[str], repository_urls: list[str | None], force_refresh: bool = False) -> list[SourceArchiveResult]`
  - `normalize_with_version(components: PurlComponents) -> str` in `purl_utils/__init__.py`

- [ ] **Step 1: Write failing tests**

```python
import pytest

from purl_resolver.settings_store import SettingsStore
from purl_resolver.source_archive.matching import TagInfo
from purl_resolver.source_archive.service import SourceArchiveService
from purl_resolver.storage.inmemory_source_archive import InMemorySourceArchiveStorage


PURL = "pkg:github/ClickHouse/ClickHouse@23.8.16.40"
REPO = "https://github.com/ClickHouse/ClickHouse"
TAGS = [TagInfo("v23.8.16.40-lts", "sha1"), TagInfo("v23.8.16.39", "sha2")]


def make_service(tmp_path, tags=TAGS, head=True):
    calls = {"tags": 0, "head": 0}

    async def fetcher(url, timeout):
        calls["tags"] += 1
        return list(tags)

    async def checker(url, timeout):
        calls["head"] += 1
        return head

    store = SettingsStore(path=tmp_path / "settings.json")
    service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=store,
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    return service, calls


@pytest.mark.asyncio
async def test_exact_match_is_stored_and_returned(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "exact"
    assert result.archive_url.endswith("/archive/refs/tags/v23.8.16.40-lts.tar.gz")
    assert result.archive_url_commit.endswith("/archive/sha1.tar.gz")
    assert result.matched_ref == "v23.8.16.40-lts"
    assert result.resolver == "git-tags"
    assert calls["tags"] == 1


@pytest.mark.asyncio
async def test_multiple_exact_tags_add_warning(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v1.2.3", "a"), TagInfo("1.2.3", "b")])
    result = await service.lookup("pkg:github/a/b@1.2.3", "https://github.com/a/b")
    assert result.matched_ref == "1.2.3"
    assert any("multiple" in w.lower() for w in result.warnings)


@pytest.mark.asyncio
async def test_second_lookup_uses_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    result = await service.lookup(PURL, REPO)
    assert result.cached is True
    assert calls["tags"] == 1


@pytest.mark.asyncio
async def test_changed_repository_url_invalidates_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    await service.lookup(PURL, "https://github.com/Other/Repo")
    assert calls["tags"] == 2


@pytest.mark.asyncio
async def test_no_version_returns_no_version_without_fetch(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    result = await service.lookup("pkg:github/ClickHouse/ClickHouse", REPO)
    assert result.match_type == "no_version"
    assert result.reason == "no_version"
    assert calls["tags"] == 0


@pytest.mark.asyncio
async def test_non_numeric_version(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup("pkg:github/a/b@main", "https://github.com/a/b")
    assert result.match_type == "repository_only"
    assert result.reason == "non_numeric_version"


@pytest.mark.asyncio
async def test_missing_repository_is_not_found(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup(PURL, None)
    assert result.match_type == "not_found"
    assert result.reason == "no_repository"


@pytest.mark.asyncio
async def test_non_github_repository(tmp_path) -> None:
    service, _ = make_service(tmp_path)
    result = await service.lookup(PURL, "https://gitlab.com/a/b")
    assert result.match_type == "repository_only"
    assert result.reason == "unsupported_host"


@pytest.mark.asyncio
async def test_git_error_falls_back_to_repository_only(tmp_path) -> None:
    async def failing_fetcher(url, timeout):
        raise RuntimeError("boom")

    async def ok_checker(url, timeout):
        return True

    service = SourceArchiveService(
        storage=InMemorySourceArchiveStorage(),
        settings_store=SettingsStore(path=tmp_path / "settings.json"),
        tag_fetcher=failing_fetcher,
        url_checker=ok_checker,
    )
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "git_error"


@pytest.mark.asyncio
async def test_near_match_when_no_exact(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v23.8.16.39", "sha2")])
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "near"
    assert result.matched_version == "23.8.16.39"


@pytest.mark.asyncio
async def test_no_matching_tag(tmp_path) -> None:
    service, _ = make_service(tmp_path, tags=[TagInfo("v1.0.0", "sha2")])
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "no_matching_tag"


@pytest.mark.asyncio
async def test_head_failure_falls_back_to_repository_only(tmp_path) -> None:
    service, _ = make_service(tmp_path, head=False)
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "repository_only"
    assert result.reason == "archive_check_failed"


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(tmp_path) -> None:
    service, calls = make_service(tmp_path)
    await service.lookup(PURL, REPO)
    await service.lookup(PURL, REPO, force_refresh=True)
    assert calls["tags"] == 2


@pytest.mark.asyncio
async def test_storage_failure_does_not_break_result(tmp_path) -> None:
    class FailingStorage(InMemorySourceArchiveStorage):
        async def store_archive(self, row):
            raise RuntimeError("db down")

        async def lookup_archive(self, purl):
            return None

    async def fetcher(url, timeout):
        return list(TAGS)

    async def checker(url, timeout):
        return True

    service = SourceArchiveService(
        storage=FailingStorage(),
        settings_store=SettingsStore(path=tmp_path / "settings.json"),
        tag_fetcher=fetcher,
        url_checker=checker,
    )
    result = await service.lookup(PURL, REPO)
    assert result.match_type == "exact"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_service.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `normalize_with_version` and the service**

- `normalize_with_version`: build `PackageURL(type, namespace, name, version=components.version).to_string()`.
- `SourceArchiveService.lookup` follows steps 1–11 of design section 6.8:
  - version checks before any network call;
  - cache lookup unless `force_refresh`; invalidate on non-null repository mismatch;
  - `no_repository` / `unsupported_host` / `git_error` / `exact` / `near` / `archive_check_failed` / `no_matching_tag` outcomes;
  - exact match ordering from Task 1; add a warning when more than one exact candidate matched;
  - `resolver="git-tags"` for every stored outcome;
  - `resolved_at` set by the service to `datetime.now(timezone.utc).isoformat()` on store.
- Wrap `tag_fetcher` failures (`GitTagsError` and unexpected exceptions) into `git_error`.
- Storage failures are logged and ignored.
- `enrich_many` runs with a semaphore from `source_archive_concurrency`, preserves input order, and deduplicates identical `(versioned purl, repository_url)` pairs.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_service.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/purl_utils src/purl_resolver/source_archive/service.py tests/test_source_archive_service.py
git commit -m "feat(source-archive): add cached deterministic archive lookup"
```

---

### Task 7: API contract and application wiring

**Files:**
- Modify: `src/purl_resolver/schemas.py`
- Modify: `src/purl_resolver/routes/resolve.py`
- Modify: `src/purl_resolver/main.py`
- Test: `tests/test_source_archive_api.py`

**Interfaces:**
- Produces:
  - `BatchResolveRequest.find_source_archive: bool = False`
  - `BatchResolveRequest.force_refresh: bool = False`
  - `BatchResolveItem.source_archive_url: str | None = None`
  - `BatchResolveItem.source_archive_commit_url: str | None = None`
  - `BatchResolveItem.source_archive_commit_sha: str | None = None`
  - `BatchResolveItem.source_archive_match: str | None = None`
  - `BatchResolveItem.source_archive_reason: str | None = None`
  - `BatchResolveItem.source_archive_ref: str | None = None`
  - `BatchResolveItem.source_archive_ref_type: str | None = None`
  - `BatchResolveItem.source_archive_matched_version: str | None = None`
  - `BatchResolveItem.source_archive_resolver: str = ""`
  - `BatchResolveItem.source_archive_cached: bool = False`
  - `BatchResolveItem.source_archive_resolved_at: str = ""`
- Produces app state `source_archive_service`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_source_archive_api.py` with a `TestClient` app that uses `InMemoryCache`, a `FakeResolver` returning the ClickHouse repo, `SettingsStore(path=tmp_path/...)`, and a `SourceArchiveService` built with fake tag fetcher/checker. Cover:

```python
def test_flag_off_keeps_response_unchanged(client):
    data = client.post("/api/v1/resolve/batch", json={"purls": [PURL]}).json()
    item = data["results"][0]
    assert item["repository_url"] == REPO
    assert item["source_archive_url"] is None
    assert item["source_archive_match"] is None


def test_flag_on_returns_exact_archive(client):
    data = client.post("/api/v1/resolve/batch", json={
        "purls": [PURL], "find_source_archive": True,
    }).json()
    item = data["results"][0]
    assert item["source_archive_match"] == "exact"
    assert item["source_archive_ref"] == "v23.8.16.40-lts"
    assert item["source_archive_url"].endswith("/archive/refs/tags/v23.8.16.40-lts.tar.gz")
    assert item["source_archive_cached"] is False


def test_second_request_is_cached(client):
    client.post("/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True})
    data = client.post("/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True}).json()
    assert data["results"][0]["source_archive_cached"] is True


def test_force_refresh_recomputes(client):
    client.post("/api/v1/resolve/batch", json={"purls": [PURL], "find_source_archive": True})
    data = client.post("/api/v1/resolve/batch", json={
        "purls": [PURL], "find_source_archive": True, "force_refresh": True,
    }).json()
    assert data["results"][0]["source_archive_cached"] is False


def test_invalid_purl_keeps_archive_fields_null(client):
    data = client.post("/api/v1/resolve/batch", json={
        "purls": ["not-a-purl"], "find_source_archive": True,
    }).json()
    assert data["results"][0]["error"] == "invalid_purl"
    assert data["results"][0]["source_archive_match"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_source_archive_api.py -q`
Expected: FAIL — unknown request fields are ignored and response fields are missing.

- [ ] **Step 3: Implement schemas, route, and wiring**

- Add flags/fields to `schemas.py` with defaults so existing responses remain valid.
- In `routes/resolve.py`, after `resolve_many`, if `find_source_archive` is true: collect `repository_url` per result, call `enrich_many`, and populate each `BatchResolveItem` by index. Do not call the archive service for rows with `error` set; leave their archive fields `None`.
- In `main.py`, create `InMemorySourceArchiveStorage` or `PostgresSourceArchiveStorage(pool)` and `SourceArchiveService`; store on `app.state.source_archive_service`.
- Keep `find_source_archive=false` behavior compatible apart from the new `null` fields.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_source_archive_api.py tests/test_api.py tests/test_resolve_batch.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/schemas.py src/purl_resolver/routes/resolve.py src/purl_resolver/main.py tests/test_source_archive_api.py
git commit -m "feat(source-archive): expose archive lookup through batch API"
```

---

### Task 8: PURL Resolver UI mode

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/api/purl.ts`
- Modify: `frontend/src/views/PurlResolver.vue`
- Modify: `frontend/src/views/PurlResolver.test.ts`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Consumes: Task 7 API fields.
- Produces: `BatchResolveRequest.find_source_archive?: boolean`, `force_refresh?: boolean`; archive fields on `BatchResolveItem`.

- [ ] **Step 1: Write failing tests**

Add to `PurlResolver.test.ts`:

```typescript
it('sends find_source_archive when the mode checkbox is checked', async () => {
  const wrapper = mountResolver()
  await flushPromises()
  await wrapper.find('textarea').setValue('pkg:github/ClickHouse/ClickHouse@23.8.16.40')
  await wrapper.find('input[type="checkbox"]').setValue(true)
  await wrapper.find('form').trigger('submit.prevent')
  await flushPromises()
  expect(resolvePurlsMock).toHaveBeenCalledWith({
    purls: ['pkg:github/ClickHouse/ClickHouse@23.8.16.40'],
    find_source_archive: true,
  })
})

it('renders archive columns and exact badge', async () => {
  resolvePurlsMock.mockResolvedValueOnce({
    results: [{
      ...successResponse.results[0],
      source_archive_url: 'https://github.com/psf/requests/archive/refs/tags/v2.31.0.tar.gz',
      source_archive_match: 'exact',
      source_archive_ref: 'v2.31.0',
      source_archive_matched_version: '2.31.0',
      source_archive_resolver: 'git-tags',
      source_archive_cached: false,
      source_archive_resolved_at: '2026-11-17T12:00:00+00:00',
    }],
  })
  const wrapper = mountResolver()
  await flushPromises()
  await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
  await wrapper.find('input[type="checkbox"]').setValue(true)
  await wrapper.find('form').trigger('submit.prevent')
  await flushPromises()
  expect(wrapper.text()).toContain('Source archive')
  expect(wrapper.text()).toContain('Exact')
  expect(wrapper.find('a[href$=".tar.gz"]').exists()).toBe(true)
})

it('renders near badge with the matched version', async () => {
  resolvePurlsMock.mockResolvedValueOnce({
    results: [{
      ...successResponse.results[0],
      source_archive_url: 'https://github.com/psf/requests/archive/refs/tags/v2.30.0.tar.gz',
      source_archive_match: 'near',
      source_archive_matched_version: '2.30.0',
    }],
  })
  const wrapper = mountResolver()
  await flushPromises()
  await wrapper.find('textarea').setValue('pkg:pypi/requests@2.31.0')
  await wrapper.find('input[type="checkbox"]').setValue(true)
  await wrapper.find('form').trigger('submit.prevent')
  await flushPromises()
  expect(wrapper.text()).toContain('Near v2.30.0')
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- PurlResolver`
Expected: FAIL — checkbox and columns missing.

- [ ] **Step 3: Implement the UI**

- Add the checkbox under the textarea; include `find_source_archive: true` in the request only when checked.
- When the mode is on, render two extra columns: archive link (or `—`) and a badge:
  `exact` → "Exact/Точная"; `near` → "Near vX/Близкая vX"; `repository_only` → "Repository only/Только репозиторий"; `not_found` → "Not found/Не найдено"; `no_version` → "No version/Нет версии".
- Show `source_archive_reason` text in the warnings cell when it is set and no warning already covers it.
- Keep the existing 6-column layout when the mode is off.
- Add all keys to both locale files under `purlResolver`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- PurlResolver`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/api/purl.ts frontend/src/views/PurlResolver.vue frontend/src/views/PurlResolver.test.ts frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat(source-archive): add version archive mode to PURL resolver UI"
```

---

### Task 9: Settings UI for archive timeout and concurrency

**Files:**
- Modify: `frontend/src/types/api.ts`
- Modify: `frontend/src/stores/useSettingsStore.ts`
- Modify: `frontend/src/views/Settings.vue`
- Modify: `frontend/src/views/Settings.test.ts`
- Modify: `frontend/src/i18n/locales/ru.json`
- Modify: `frontend/src/i18n/locales/en.json`

**Interfaces:**
- Produces: `SettingsResponse.source_archive_timeout`, `SettingsResponse.source_archive_concurrency`, matching optional `SettingsUpdate` fields, and store refs `sourceArchiveTimeout`, `sourceArchiveConcurrency`.

- [ ] **Step 1: Write failing tests**

Add to `Settings.test.ts`: load returns `source_archive_timeout: 30`, `source_archive_concurrency: 5`; changing the timeout input auto-saves `{ source_archive_timeout: 45 }`; changing concurrency auto-saves `{ source_archive_concurrency: 8 }`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm --prefix frontend run test -- Settings`
Expected: FAIL — fields are undefined.

- [ ] **Step 3: Implement settings UI**

- Add types and store refs/loading.
- Add two numeric rows in the "Network & Performance" card: timeout 1–300 (step 0.5) and concurrency 1–50.
- Add `settings.network.sourceArchiveTimeout`, `sourceArchiveTimeoutDesc`, `sourceArchiveConcurrency`, `sourceArchiveConcurrencyDesc` to both locales.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm --prefix frontend run test -- Settings`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/stores/useSettingsStore.ts frontend/src/views/Settings.vue frontend/src/views/Settings.test.ts frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat(source-archive): expose archive settings in UI"
```

---

### Task 10: Backup script exports both tables

**Files:**
- Modify: `scripts/db_backup.sh`
- Modify: `tests/test_db_backup_scripts.py`

**Interfaces:**
- Produces: second file `*.source_archives.csv.gz` with header
  `purl,version,match_type,reason,archive_url,archive_url_commit,matched_ref,matched_ref_type,matched_version,repository_url,resolver,resolved_at`.

- [ ] **Step 1: Write failing tests**

Add a docker-gated test that seeds one archive row, runs `db_backup.sh -o out.csv.gz`, and asserts:
- both `out.csv.gz` and `out.source_archives.csv.gz` exist with mode `0600`;
- the second header matches exactly and the seeded row round-trips;
- stdout mentions both files and `archives rows: 1`;
- with default output names, both files share the same timestamp suffix;
- `--keep 1` after a second run leaves one pair and removes the older pair.

Use a `_write_archive_rows` helper and the existing `_read_backup`, `_psql`, `_run_script` helpers; truncate `purl_source_archives` in `_seed`.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -q`
Expected: FAIL — second file missing.

- [ ] **Step 3: Implement backup changes**

- Build the archive path from `-o`: insert `.source_archives` before `.csv.gz`; with defaults use `sbom_source_archives_<same timestamp>.csv.gz`.
- `COPY (SELECT purl, version, match_type, reason, archive_url, archive_url_commit, matched_ref, matched_ref_type, matched_version, repository_url, resolver, resolved_at FROM purl_source_archives ORDER BY purl) TO STDOUT WITH (FORMAT csv, HEADER true)`.
- `--keep N` counts pairs by timestamp and removes both files of older pairs; handle orphan files.
- Print both paths, both row counts, and keep the existing exit-on-error behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -q`
Expected: PASS (or skipped when docker is unavailable).

- [ ] **Step 5: Commit**

```bash
git add scripts/db_backup.sh tests/test_db_backup_scripts.py
git commit -m "feat(source-archive): back up archive cache"
```

---

### Task 11: Restore script handles both tables

**Files:**
- Modify: `scripts/db_restore.sh`
- Modify: `tests/test_db_backup_scripts.py`
- Modify: `frontend/src/components/db/DbBackupHelp.vue`
- Modify: `README.md`

**Interfaces:**
- Restore accepts one or two files; identifies the table by exact header.
- `merge`: `ON CONFLICT (purl) DO NOTHING`; `replace`: `TRUNCATE` + insert in one transaction, reject an empty file.

- [ ] **Step 1: Write failing tests**

Add docker-gated tests:
- restore a `purl_source_archives` file alone (merge) adds missing rows and keeps an existing row unchanged;
- restore both files in one invocation updates both tables;
- `--mode replace --yes` replaces the archive table and deletes rows missing from the file;
- an archive file with a wrong header is rejected without touching either table;
- an empty archive file with `--mode replace` is refused;
- no staging tables remain after any failure.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -q`
Expected: FAIL — archive file is rejected as unknown header.

- [ ] **Step 3: Implement restore changes**

- Detect table by exact header for both tables; accept files in either order.
- Use per-table staging names `resolved_purls_import_<pid>` and `purl_source_archives_import_<pid>`.
- Print `mode`, file, and `inserted/skipped/total` per table.
- Update `DbBackupHelp.vue` and `README.md` to mention the second file and the two-file restore.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_db_backup_scripts.py -q`
Expected: PASS (or skipped when docker is unavailable).

- [ ] **Step 5: Commit**

```bash
git add scripts/db_restore.sh tests/test_db_backup_scripts.py frontend/src/components/db/DbBackupHelp.vue README.md
git commit -m "feat(source-archive): restore archive cache from backup"
```

---

### Task 12: Specifications update and full verification

**Files:**
- Modify: `specs/domains/purl-resolution.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/architecture/layers.md`
- Modify: `specs/INDEX.md`
- Create: `specs/decisions/0009-source-archive-links.md`

**Interfaces:**
- None (documentation task).

- [ ] **Step 1: Update existing specs**

Use the `vibespec-update` skill. Add to `purl-resolution.md`: source archive resolution flow, `purl_source_archives` schema, match types/reasons, settings, cache invalidation. Add request/response fields and an example to `api-contract.md`. Add the mode/columns to `web-ui.md`. Add `SourceArchiveService` and `SourceArchiveStorage` to `layers.md`. Update `INDEX.md` if its task mapping needs a row.

- [ ] **Step 2: Create the ADR**

Use the `vibespec-create` skill to add `specs/decisions/0009-source-archive-links.md` covering: separate table vs extending `resolved_purls`, `git ls-remote` vs GitHub API, deterministic matching without LLM in v1, negative caching, and the GitHub-only first version.

- [ ] **Step 3: Run the full backend suite**

Run: `.venv/bin/python -m pytest -q`
Expected: PASS. If only `tests/e2e/` fails on external timeouts, rerun `SKIP_E2E=1 .venv/bin/python -m pytest -q` and record the result.

- [ ] **Step 4: Run frontend checks**

Run: `npm --prefix frontend run test`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: successful build with no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add specs frontend/src
git commit -m "docs(source-archive): document version archive links"
```

---

## Self-Review Notes

- **Spec coverage:** matching (§6.5), git tags (§6.6), GitHub URLs (§6.7), service/cache (§6.8), API (§6.9), settings (§6.10), UI (§6.11), backup/restore (§6.12), specs (§6.13) each have a task.
- **Type consistency:** `TagInfo`/`TagMatch` flow from Task 1 through Tasks 2 and 6; `SourceArchiveRow` is produced in Task 4 and consumed in Task 6; API field names in Task 7 match Task 8 types.
- **Review Focus mapping:** no-version/non-numeric → Task 6 tests; odd/large tags → Tasks 1–3; repository change → Task 6; redirects → Task 3; DB unavailable/storage failure → Task 6 tests and Task 4 in-memory fallback.
- **Deliberate omissions:** exact wording of i18n strings and the internal split of `service.py` are left to the implementer as the design allows.
