# LLM Resolver TLS Trust Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow the LLM resolver's OpenAI-compatible client to trust a corporate CA bundle or fully disable TLS certificate verification, configurable via the Settings UI and applied without restart.

**Architecture:** Add two settings (`llm_resolver_verify_ssl`, `llm_resolver_ca_bundle`) to `AppSettings`, thread them through the settings API, and have `LlmResolver` build a single `verify` value (`True` / `ssl.SSLContext`) used by both its `AsyncOpenAI` `http_client` and its HEAD-check `httpx.AsyncClient`. Also set `max_retries=0` on `AsyncOpenAI` and surface the underlying error reason in warnings.

**Tech Stack:** Python 3.11+, FastAPI/Pydantic, httpx 0.28.1, openai 3.3.1, Vue 3 + Pinia + vue-i18n, vitest.

**Spec:** `docs/superpowers/specs/2026-11-28-llm-resolver-tls-trust-design.md`

## Global Constraints

- Every touched Python file already uses `from __future__ import annotations` (keep it).
- Lines ≤ 100 chars; ruff config selects `E, F, I, W` (`ruff check` must stay clean).
- `AsyncOpenAI` has **no** `verify` parameter — TLS is configured only via `http_client`.
- New setting names use the `llm_resolver_*` prefix.
- Do not log API keys; do not commit PEM files or CA content to the repo.
- Backend tests: `.venv/bin/python -m pytest -q` (if only e2e fails on network, rerun `SKIP_E2E=1`).
- Frontend: `npm --prefix frontend run test` and `npm --prefix frontend run build` must pass.
- Develop directly on `main`; each task ends with a local commit (no push).

## Review Focus

1. **Nonexistent CA bundle path** must not break the resolver chain: fall back to default verification and log a warning (Task 2).
2. **`verify_ssl=false` must win over a leftover `ca_bundle`**: verification is disabled, not silently re-enabled via the CA file (Task 2).
3. **`max_retries=0`** so `llm_resolver_attempts_count` is the sole source of retry count (Task 2).
4. **Empty-string `ca_bundle`** (UI sends `null`, but PATCH may send `""`) is treated as unset (Task 2).
5. **API key is never returned in the settings body**; `ca_bundle` is returned as plain text (not secret) (Task 4).

---

### Task 1: Settings model — TLS fields

**Files:**
- Modify: `src/purl_resolver/settings_store.py` (`AppSettings`, after `llm_resolver_timeout`)
- Test: `tests/test_settings_store.py` (`TestLlmResolverSettings`)

**Interfaces:**
- Produces: `AppSettings.llm_resolver_verify_ssl: bool` (default `True`), `AppSettings.llm_resolver_ca_bundle: str | None` (default `None`).

- [ ] **Step 1: Write the failing tests**

Append to `TestLlmResolverSettings` in `tests/test_settings_store.py`:

```python
def test_tls_defaults(self) -> None:
    s = AppSettings()
    assert s.llm_resolver_verify_ssl is True
    assert s.llm_resolver_ca_bundle is None

def test_tls_roundtrip(self, tmp_path: Path) -> None:
    store = SettingsStore(path=tmp_path / "settings.json")
    settings = store.load()
    updated = settings.model_copy(update={
        "llm_resolver_verify_ssl": False,
        "llm_resolver_ca_bundle": "/etc/ssl/corp-ca.pem",
    })
    store.save(updated)
    loaded = store.load()
    assert loaded.llm_resolver_verify_ssl is False
    assert loaded.llm_resolver_ca_bundle == "/etc/ssl/corp-ca.pem"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py -q`
Expected: FAIL (attributes missing / unexpected extra fields).

- [ ] **Step 3: Add the two fields to `AppSettings`**

In `src/purl_resolver/settings_store.py`, after `llm_resolver_timeout` add:

```python
llm_resolver_verify_ssl: bool = True
llm_resolver_ca_bundle: str | None = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_settings_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/settings_store.py tests/test_settings_store.py
git commit -m "feat: add LLM resolver TLS trust settings to AppSettings"
```

---

### Task 2: LlmResolver — TLS context, retries, error reason

**Files:**
- Modify: `src/purl_resolver/resolver/llm.py` (`LlmResolver.__init__`, `_request`, `resolve`)
- Test: `tests/test_llm_resolver.py`

**Interfaces:**
- Consumes: `AppSettings` fields (Task 1) via factory (Task 3); here the constructor params only.
- Produces: module function `_build_ssl_verify(verify_ssl: bool, ca_bundle: str | None) -> bool | ssl.SSLContext`; `LlmResolver.__init__(..., verify_ssl: bool = True, ca_bundle: str | None = None)`; `LlmResolver._request(...) -> tuple[str | None, str | None]` (content, error reason).

- [ ] **Step 1: Write the failing tests**

Add a module constant near the top of `tests/test_llm_resolver.py`:

```python
_TEST_CA_PEM = """-----BEGIN CERTIFICATE-----
MIIDBTCCAe2gAwIBAgIUOVjTn3UjbzM9+V12JP+mDSIYdMQwDQYJKoZIhvcNAQEL
BQAwEjEQMA4GA1UEAwwHdGVzdC1jYTAeFw0yNjExMjgxMTU4NDJaFw0zNjExMjUx
MTU4NDJaMBIxEDAOBgNVBAMMB3Rlc3QtY2EwggEiMA0GCSqGSIb3DQEBAQUAA4IB
DwAwggEKAoIBAQDAHmd2osRANdzgT1lPITOKQYLsMwFhiXytRMrkWhJcQSTiRNdC
8xIBiIl+rWbWyHDRxM+ERGg1jfHO/jjDKw6mf+KsRVuGSnfqjKgS8OojpuYDbHWb
ohZbkkcF9FhriC6L13OcFp6Qo+DjVHrJf16dUe0/QP0rfDVuFBmqRLwER+7VEW3E
Lel9SOyoKOeaxhCdJ2CRUaYUR4Ms1tad50esiNb8CwzFe6Xsoxk6ATYOUD45Cjh6
kg6x0ZhZntxNv6TKC7cr2pzEy6FuDEWv8CQQlDjUVEhpJhmJOZcJdl0bp97Ob5yT
SFeDnmscYOIci+cjnyS8ydKdV+3UwPHhvRIDAgMBAAGjUzBRMB0GA1UdDgQWBBS3
XwBW8V5ArDAYofilBYnsua+/9TAfBgNVHSMEGDAWgBS3XwBW8V5ArDAYofilBYns
ua+/9TAPBgNVHRMBAf8EBTADAQH/MA0GCSqGSIb3DQEBCwUAA4IBAQAJUH6ncrcw
IIrPLpAo/UXcr2dIs+cf4b4JtvNfuM0Q5My5xUOMwo387xcX6HH2bjuBbP/2YHja
oKdG2NAxBaMRhvvhQqkY63Y19C5r3wVT/fyC3pmcvtXg4p0nSW77v9t1N6Kj6SPY
cm+s5F8Xzj9I5v9U8lzksKmXh0r98CVhTalHI6bq2hBaaAlBQWdSj7/s7oxDG2/i
QhTdJzTKWSEjupIgo6neGUKsE+2ti7BE5RG4qinRlTDEkIStxAAizk3L75PO3FQV
eoFy088URbNmOBq/FilIrFyGfnKXY/FFjhdGMD6d+NhkqOomY2ttcrUXrwvyYHd7
ISDO4sIiueAz
-----END CERTIFICATE-----
"""
```

Add `import ssl` to the test imports. Add a new class:

```python
class TestTlsConfiguration:
    def test_default_verification_is_true(self) -> None:
        assert _build_ssl_verify(True, None) is True

    def test_verify_disabled_returns_cert_none_context(self) -> None:
        ctx = _build_ssl_verify(False, None)
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_verify_disabled_ignores_ca_bundle(self) -> None:
        ctx = _build_ssl_verify(False, "/etc/ssl/corp-ca.pem")
        assert isinstance(ctx, ssl.SSLContext)
        assert ctx.verify_mode == ssl.CERT_NONE

    def test_empty_ca_bundle_is_unset(self) -> None:
        assert _build_ssl_verify(True, "") is True

    def test_ca_bundle_loaded_returns_context(self, tmp_path) -> None:
        ca_file = tmp_path / "ca.pem"
        ca_file.write_text(_TEST_CA_PEM)
        ctx = _build_ssl_verify(True, str(ca_file))
        assert isinstance(ctx, ssl.SSLContext)
        assert len(ctx.get_ca_certs()) >= 1

    def test_missing_ca_bundle_falls_back_and_warns(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging
        with caplog.at_level(logging.WARNING, logger="purl_resolver.resolver.llm"):
            assert _build_ssl_verify(True, "/nonexistent/ca.pem") is True
        assert any("CA bundle" in m for m in caplog.messages)

    def test_client_created_with_max_retries_zero(self) -> None:
        with patch("purl_resolver.resolver.llm.AsyncOpenAI") as client_cls:
            LlmResolver(base_url=_BASE_URL, api_key=_API_KEY, model=_MODEL)
        kwargs = client_cls.call_args.kwargs
        assert kwargs["max_retries"] == 0
        assert "http_client" in kwargs

    @pytest.mark.asyncio
    async def test_connection_error_reason_surfaces_in_warnings(self) -> None:
        resolver, create, _ = make_llm_resolver(attempts_count=1)
        create.side_effect = httpx.ConnectError(
            "CERTIFICATE_VERIFY_FAILED self-signed certificate"
        )
        result = await resolver.resolve(_PURL)
        assert result.repository_url is None
        assert any("CERTIFICATE_VERIFY_FAILED" in w for w in result.warnings)
        assert any("ConnectError" in w for w in result.warnings)
```

Add `from unittest.mock import patch` and `from purl_resolver.resolver.llm import LlmResolver, _build_ssl_verify` to the imports (extend the existing `LlmResolver` import).

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py -q`
Expected: FAIL (import error: `_build_ssl_verify` undefined).

- [ ] **Step 3: Implement the TLS logic in `src/purl_resolver/resolver/llm.py`**

Add `import ssl` (with the other stdlib imports). Add the module-level function after `_RETRY_FEEDBACK`:

```python
def _build_ssl_verify(verify_ssl: bool, ca_bundle: str | None) -> bool | ssl.SSLContext:
    if not verify_ssl:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        logger.warning("LLM resolver: TLS certificate verification is disabled")
        return context
    if ca_bundle:
        try:
            return ssl.create_default_context(cafile=ca_bundle)
        except OSError as exc:
            logger.warning(
                "LLM resolver: cannot load CA bundle %s (%s); falling back to default verification",
                ca_bundle, exc,
            )
    return True
```

Change the constructor signature and body: add `verify_ssl: bool = True, ca_bundle: str | None = None` after `timeout`; replace the two client creations:

```python
self._verify = _build_ssl_verify(verify_ssl, ca_bundle)
self._client = AsyncOpenAI(
    base_url=base_url,
    api_key=api_key,
    timeout=timeout,
    max_retries=0,
    http_client=httpx.AsyncClient(
        verify=self._verify, timeout=timeout, follow_redirects=True
    ),
)
self._http_client = httpx.AsyncClient(
    verify=self._verify, timeout=timeout, follow_redirects=True
)
```

Change `_request` to return `tuple[str | None, str | None]`:

```python
async def _request(self, messages: list[dict[str, str]]) -> tuple[str | None, str | None]:
    try:
        completion = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
        )
        return completion.choices[0].message.content, None
    except (APIError, httpx.HTTPError) as exc:
        reason = f"LLM request failed ({type(exc).__name__}: {exc})"
        logger.warning("%s", reason)
        return None, reason
```

Change the caller in `resolve`:

```python
content, error = await self._request(messages)
if content is None:
    self._record_failure(warnings, messages, attempt, purl, error or "LLM request failed")
    continue
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py -q`
Expected: PASS (all existing + new).

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/llm.py tests/test_llm_resolver.py
git commit -m "feat: configurable TLS trust and retry control for LLM resolver"
```

---

### Task 3: Factory pass-through

**Files:**
- Modify: `src/purl_resolver/resolver/factory.py` (`LlmResolver(...)` call)
- Test: `tests/test_llm_resolver.py` (`TestFactory`)

**Interfaces:**
- Consumes: `_build_ssl_verify`/`LlmResolver` constructor params (Task 2), `AppSettings` fields (Task 1).
- Produces: `LlmResolver` is constructed with `verify_ssl` and `ca_bundle` kwargs.

- [ ] **Step 1: Write the failing test**

Add to `TestFactory` in `tests/test_llm_resolver.py`:

```python
def test_factory_passes_tls_settings(self) -> None:
    from purl_resolver.config import Settings
    from purl_resolver.resolver.factory import build_resolvers
    from purl_resolver.settings_store import AppSettings

    app_settings = AppSettings(
        ecosystems_enabled=False,
        librariesio_enabled=False,
        llm_resolver_enabled=True,
        llm_resolver_base_url=_BASE_URL,
        llm_resolver_api_key=_API_KEY,
        llm_resolver_model=_MODEL,
        llm_resolver_verify_ssl=False,
        llm_resolver_ca_bundle="/etc/ssl/corp-ca.pem",
    )
    with patch("purl_resolver.resolver.factory.LlmResolver") as llm_cls:
        llm_cls.return_value.name = "llm"
        build_resolvers(Settings(), app_settings)
    kwargs = llm_cls.call_args.kwargs
    assert kwargs["verify_ssl"] is False
    assert kwargs["ca_bundle"] == "/etc/ssl/corp-ca.pem"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py::TestFactory -q`
Expected: FAIL (unexpected kwargs / assertion error).

- [ ] **Step 3: Pass the fields in `build_resolvers`**

In `src/purl_resolver/resolver/factory.py`, add to the `LlmResolver(...)` call:

```python
verify_ssl=app_settings.llm_resolver_verify_ssl,
ca_bundle=app_settings.llm_resolver_ca_bundle,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_llm_resolver.py::TestFactory -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/resolver/factory.py tests/test_llm_resolver.py
git commit -m "feat: thread LLM resolver TLS settings through factory"
```

---

### Task 4: Settings API — GET/PATCH

**Files:**
- Modify: `src/purl_resolver/routes/settings.py` (`SettingsUpdate`, `get_settings`, `update_settings`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `AppSettings` fields (Task 1).
- Produces: `GET /api/v1/settings` and `PATCH /api/v1/settings` include `llm_resolver_verify_ssl` and `llm_resolver_ca_bundle`.

- [ ] **Step 1: Write the failing tests**

Add a new class to `tests/test_api.py` (near `TestLibrariesIoSettings`):

```python
class TestLlmResolverTlsSettings:
    def test_get_settings_includes_llm_tls_fields(self, client: TestClient) -> None:
        data = client.get("/api/v1/settings").json()
        assert data["llm_resolver_verify_ssl"] is True
        assert data["llm_resolver_ca_bundle"] is None
        assert "llm_resolver_api_key" not in data

    def test_patch_settings_llm_tls_fields(self, client: TestClient, tmp_path: Path) -> None:
        client.app.state.settings_store = SettingsStore(path=tmp_path / "settings.json")
        response = client.patch("/api/v1/settings", json={
            "llm_resolver_verify_ssl": False,
            "llm_resolver_ca_bundle": "/etc/ssl/corp-ca.pem",
        })
        assert response.status_code == 200
        data = response.json()
        assert data["llm_resolver_verify_ssl"] is False
        assert data["llm_resolver_ca_bundle"] == "/etc/ssl/corp-ca.pem"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_api.py::TestLlmResolverTlsSettings -q`
Expected: FAIL (KeyError on `llm_resolver_verify_ssl`).

- [ ] **Step 3: Add fields to `SettingsUpdate` and both handlers**

In `src/purl_resolver/routes/settings.py`:
- Add to `SettingsUpdate` (after `llm_resolver_timeout`):

```python
llm_resolver_verify_ssl: bool | None = None
llm_resolver_ca_bundle: str | None = None
```

- In `get_settings` response dict, after `"llm_resolver_timeout"` add:

```python
"llm_resolver_verify_ssl": app_settings.llm_resolver_verify_ssl,
"llm_resolver_ca_bundle": app_settings.llm_resolver_ca_bundle,
```

- In `update_settings` response dict, after `"llm_resolver_timeout"` add:

```python
"llm_resolver_verify_ssl": updated.llm_resolver_verify_ssl,
"llm_resolver_ca_bundle": updated.llm_resolver_ca_bundle,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/purl_resolver/routes/settings.py tests/test_api.py
git commit -m "feat: expose LLM resolver TLS trust settings via API"
```

---

### Task 5: Frontend — types, store, view, i18n, tests

**Files:**
- Modify: `frontend/src/types/api.ts`, `frontend/src/stores/useSettingsStore.ts`, `frontend/src/views/Settings.vue`, `frontend/src/i18n/locales/en.json`, `frontend/src/i18n/locales/ru.json`
- Test: `frontend/src/views/Settings.test.ts`

**Interfaces:**
- Consumes: API fields `llm_resolver_verify_ssl`, `llm_resolver_ca_bundle` (Task 4).
- Produces: `SettingsResponse.llm_resolver_verify_ssl: boolean`, `SettingsResponse.llm_resolver_ca_bundle: string | null`; `SettingsUpdate` optional equivalents; store refs `llmVerifySsl`, `llmCaBundle`.

- [ ] **Step 1: Add types and store refs**

In `frontend/src/types/api.ts`:
- `SettingsResponse` (after `llm_resolver_timeout`): add `llm_resolver_verify_ssl: boolean` and `llm_resolver_ca_bundle: string | null`.
- `SettingsUpdate` (after `llm_resolver_timeout?`): add `llm_resolver_verify_ssl?: boolean` and `llm_resolver_ca_bundle?: string | null`.

In `frontend/src/stores/useSettingsStore.ts`:
- Add refs after `llmTimeout`: `const llmVerifySsl = ref(true)` and `const llmCaBundle = ref('')`.
- In `load()`, after `llmTimeout.value = data.llm_resolver_timeout` add:
  `llmVerifySsl.value = data.llm_resolver_verify_ssl` and
  `llmCaBundle.value = data.llm_resolver_ca_bundle ?? ''`.
- Add `llmVerifySsl, llmCaBundle` to the returned object (both the destructure block near the bottom and `storeToRefs` usage in `Settings.vue`).

- [ ] **Step 2: Add UI controls in `frontend/src/views/Settings.vue`**

Add `llmVerifySsl, llmCaBundle` to the `storeToRefs(store)` destructure. After the timeout `setting-row` in the LLM card (before the card's closing `</div>`), add:

```html
<div class="setting-row" :class="{ 'setting-disabled': !llmEnabled }">
  <div>
    <div class="setting-label">{{ t('settings.llmResolver.verifySsl') }}</div>
    <div class="setting-desc">{{ t('settings.llmResolver.verifySslDesc') }}</div>
  </div>
  <label class="toggle">
    <input type="checkbox" v-model="llmVerifySsl" :disabled="!llmEnabled" @change="debouncedAutoSave({ llm_resolver_verify_ssl: llmVerifySsl })">
    <span class="toggle-slider"></span>
  </label>
</div>
<div class="setting-row" :class="{ 'setting-disabled': !llmEnabled || !llmVerifySsl }">
  <div>
    <div class="setting-label">{{ t('settings.llmResolver.caBundle') }}</div>
    <div class="setting-desc">{{ t('settings.llmResolver.caBundleDesc') }}</div>
  </div>
  <input type="text" v-model="llmCaBundle" :disabled="!llmEnabled || !llmVerifySsl" @blur="debouncedAutoSave({ llm_resolver_ca_bundle: llmCaBundle || null })" class="txt-input">
</div>
```

- [ ] **Step 3: Add i18n keys**

In `frontend/src/i18n/locales/en.json` inside `settings.llmResolver` (after `"timeoutDesc"`):

```json
"verifySsl": "Verify TLS certificate",
"verifySslDesc": "Validate the LLM endpoint's TLS certificate against the trusted CA bundle. Disable only as a temporary measure for internal LLM endpoints behind a self-signed certificate.",
"caBundle": "CA bundle path (PEM)",
"caBundleDesc": "Filesystem path inside the container to a PEM file with the corporate root/intermediate CA, used when TLS verification is enabled. Leave empty to use the default system CA bundle."
```

In `frontend/src/i18n/locales/ru.json` inside `settings.llmResolver` (after `"timeoutDesc"`):

```json
"verifySsl": "Проверять TLS-сертификат",
"verifySslDesc": "Проверять TLS-сертификат эндпоинта LLM по доверенному CA-бандлу. Отключайте только как временную меру для внутренних LLM за самоподписанным сертификатом.",
"caBundle": "Путь к CA-бандлу (PEM)",
"caBundleDesc": "Путь в файловой системе контейнера к PEM-файлу с корпоративным корневым/промежуточным CA. Используется при включённой проверке TLS. Оставьте пустым для системного CA-бандла по умолчанию."
```

- [ ] **Step 4: Update frontend tests**

In `frontend/src/views/Settings.test.ts`:
- Add to `defaultSettings` (after `llm_resolver_timeout: 60`): `llm_resolver_verify_ssl: true, llm_resolver_ca_bundle: null`.
- Add a helper next to `findNumberInputByLabel`:

```ts
function findTextInputByLabel(wrapper: VueWrapper, label: string) {
  const row = wrapper.findAll('.setting-row').find((item) => item.find('.setting-label').exists() && item.find('.setting-label').text() === label)
  expect(row).toBeDefined()
  return row!.find<HTMLInputElement>('input[type="text"]')
}
```

- Add a test:

```ts
it('renders and auto-saves LLM TLS controls', async () => {
  vi.useFakeTimers()
  try {
    const store = useSettingsStore()
    const wrapper = mountSettings()
    await flushPromises()
    store.llmEnabled = true
    await flushPromises()

    const caInput = findTextInputByLabel(wrapper, 'CA bundle path (PEM)')
    await caInput.setValue('/etc/ssl/corp-ca.pem')
    await caInput.trigger('blur')
    await flush(500)
    expect(successUpdate).toHaveBeenCalledWith({ llm_resolver_ca_bundle: '/etc/ssl/corp-ca.pem' })

    const verifyRow = wrapper.findAll('.setting-row').find((r) => r.find('.setting-label').text() === 'Verify TLS certificate')
    expect(verifyRow).toBeDefined()
    const verifyInput = verifyRow!.find<HTMLInputElement>('input[type="checkbox"]')
    await verifyInput.setValue(false)
    await flush(500)
    expect(successUpdate).toHaveBeenCalledWith({ llm_resolver_verify_ssl: false })
  } finally {
    vi.useRealTimers()
  }
})
```

- [ ] **Step 5: Run frontend tests and build**

Run: `npm --prefix frontend run test`
Expected: PASS.

Run: `npm --prefix frontend run build`
Expected: builds without type errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/stores/useSettingsStore.ts frontend/src/views/Settings.vue frontend/src/i18n/locales/en.json frontend/src/i18n/locales/ru.json frontend/src/views/Settings.test.ts
git commit -m "feat: add LLM resolver TLS trust controls to Settings UI"
```

---

### Task 6: Documentation and spec update (run after all code tasks pass)

**Files:**
- Modify: `README.md` (Settings table + a note), `specs/decisions/0008-llm-as-last-resort-resolver.md`

**Interfaces:**
- Consumes: final behavior from Tasks 1–5.

- [ ] **Step 1: Update README**

In `README.md`, extend the LLM resolver row in the Settings table (line 137) to mention the two new fields, and add one short sentence after the table describing the corporate-CA scenario: use `llm_resolver_ca_bundle` with a mounted PEM of the root CA; `verify_ssl=false` is a temporary fallback. Keep the row concise.

- [ ] **Step 2: Update ADR-0008 (use vibespec-update skill)**

Load `superpowers:use_skill` `vibespec-update`, then update `specs/decisions/0008-llm-as-last-resort-resolver.md`: add `llm_resolver_verify_ssl` (default `true`) and `llm_resolver_ca_bundle` to the Settings list in the Decision section, and a line in Consequences/Rationale noting outbound TLS trust is configurable (CA bundle recommended; `verify_ssl=false` temporary).

- [ ] **Step 3: Verify and commit**

Run: `.venv/bin/python -m pytest -q` and `npm --prefix frontend run build` (both should already be green).
Commit:

```bash
git add README.md specs/decisions/0008-llm-as-last-resort-resolver.md
git commit -m "docs: document LLM resolver TLS trust settings"
```

---

## Self-Review Notes

- Spec coverage: every design section (settings model, resolver TLS + retries + error reason, factory, routes, frontend types/store/view/i18n, tests, docs/specs) maps to a task above.
- Precedence decision `verify_ssl=false` wins over `ca_bundle` is pinned by `test_verify_disabled_ignores_ca_bundle` and encoded in the `_build_ssl_verify` ordering.
- Error-reason change keeps the `"LLM request failed"` substring so `test_api_error_exhausts_attempts` still passes.
