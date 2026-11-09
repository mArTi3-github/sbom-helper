# components.lowercase_purl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a default-on `components.lowercase_purl` fix rule with `sbom_checker` / `purl_spec` modes that lowercases only the PURL fields each mode permits.

**Architecture:** A new `purl_utils/case_rules.py` owns the two mode tables and a surgical PURL rewriter that changes only `namespace` / `name` / `version` and preserves qualifiers and subpath verbatim. `sbom/fixer.py` adds the two option fields, the rule, and a per-component call. The frontend adds the catalog entry, a radio selector under the rule row, bilingual help, and the matching tests.

**Tech Stack:** Python 3.12, Pydantic v2, `packageurl-python 0.17.6`, pytest, ruff; Vue 3, TypeScript, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-07-sbom-fixer-purl-case-design.md`

## Global Constraints

- Run Python through `.venv/bin/python`; never install packages outside `.venv`.
- Backend test command: `.venv/bin/python -m pytest -q`. If only `tests/e2e/` fail on external network, rerun with `SKIP_E2E=1 .venv/bin/python -m pytest -q`.
- Frontend test command: `npm --prefix frontend run test`; build command: `npm --prefix frontend run build`.
- Lint command: `.venv/bin/python -m ruff check src tests`.
- Local commits only; do not push or merge.
- Defaults: `components.lowercase_purl = True`, `components.purl_case_mode = "sbom_checker"`.
- Scope is the root `components[]` tree at every nesting level; `metadata.component` is never touched.
- Do not add code comments unless the user asks.
- Mode values are exactly `"sbom_checker"` and `"purl_spec"`.

## Review Focus

1. Percent-encoded uppercase characters (for example `%41`) in a permitted field are detected and lowercased, while qualifier/subpath encoding and case are preserved verbatim.
2. npm scopes (`@scope/name`) and PURLs without a version are parsed and rebuilt without losing or corrupting the scope, name, or version.
3. In `purl_spec` mode, case-sensitive identifiers (`golang`, `npm`, `gem`) are never lowercased; in `sbom_checker` mode they are lowercased by design.
4. `cpan` namespace is never lowercased in either mode, including when it is already lowercase.
5. Unknown/custom PURL types and invalid PURLs are skipped without raising and without changing the document.

---

### Task 1: PURL case rules module

**Files:**
- Create: `src/purl_resolver/purl_utils/case_rules.py`
- Create: `tests/test_purl_case_rules.py`
- Modify: `pyproject.toml:12`

**Interfaces:**
- Consumes: `packageurl.PackageURL`, `packageurl.quote`, `packageurl.unquote`, `packageurl.validate.DEFINITIONS_BY_TYPE`.
- Produces: `PurlCaseMode = Literal["sbom_checker", "purl_spec"]` and `lowercase_purl(purl: str, mode: PurlCaseMode) -> str | None`. `None` means "not a valid PURL" or "no permitted field changed".

- [ ] **Step 1: Write the failing tests**

Create `tests/test_purl_case_rules.py` with these tests:

```python
import pytest

from purl_resolver.purl_utils.case_rules import lowercase_purl


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:deb/Ubuntu/OpenSSL@3.0", "pkg:deb/ubuntu/openssl@3.0"),
        (
            "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0",
            "pkg:golang/github.com/masterminds/semver@v3.0.0",
        ),
        ("pkg:gem/Rails@7.0.0", "pkg:gem/rails@7.0.0"),
        ("pkg:npm/MyScope/Left-Pad@1.0.0", "pkg:npm/myscope/left-pad@1.0.0"),
        ("pkg:npm/@Angular/Animation", "pkg:npm/%40angular/animation"),
        ("pkg:pypi/Django_X@1.0RC1", "pkg:pypi/django_x@1.0RC1"),
        (
            "pkg:oci/Ubuntu@SHA256:ABC?tag=V1",
            "pkg:oci/ubuntu@SHA256:ABC?tag=V1",
        ),
        (
            "pkg:hackage/User/Some_Package@1.0",
            "pkg:hackage/user/Some_Package@1.0",
        ),
        (
            "pkg:vscode-extension/Microsoft/VSCode-Python@1.0.0",
            "pkg:vscode-extension/microsoft/vscode-python@1.0.0",
        ),
        (
            "pkg:deb/Ubuntu/OpenSSL@3.0?Arch=AMD64#src/Lib",
            "pkg:deb/ubuntu/openssl@3.0?Arch=AMD64#src/Lib",
        ),
        (
            "pkg:cargo/NameSpace/NamePart@1.0",
            "pkg:cargo/namespace/NamePart@1.0",
        ),
        (
            "pkg:rpm/NameSpace/NamePart@1.0",
            "pkg:rpm/namespace/NamePart@1.0",
        ),
    ],
)
def test_checker_mode_lowercases_only_allowed_fields(purl, expected):
    assert lowercase_purl(purl, "sbom_checker") == expected


@pytest.mark.parametrize(
    ("purl", "expected"),
    [
        ("pkg:deb/Ubuntu/OpenSSL@3.0", "pkg:deb/ubuntu/openssl@3.0"),
        ("pkg:pypi/Django_X@1.0RC1", "pkg:pypi/django_x@1.0rc1"),
        (
            "pkg:oci/Ubuntu@SHA256:ABC?tag=V1",
            "pkg:oci/ubuntu@sha256:abc?tag=V1",
        ),
        (
            "pkg:huggingface/User/Model@V1.0",
            "pkg:huggingface/User/Model@v1.0",
        ),
        (
            "pkg:vscode-extension/Microsoft/VSCode-Python@1.0.0",
            "pkg:vscode-extension/microsoft/vscode-python@1.0.0",
        ),
        (
            "pkg:bitnami/NamePart@1.0",
            "pkg:bitnami/namepart@1.0",
        ),
        (
            "pkg:chrome-extension/NamePart@1.0",
            "pkg:chrome-extension/namepart@1.0",
        ),
        (
            "pkg:yocto/NameSpace/NamePart@1.0",
            "pkg:yocto/namespace/NamePart@1.0",
        ),
    ],
)
def test_purl_spec_mode_lowercases_only_allowed_fields(purl, expected):
    assert lowercase_purl(purl, "purl_spec") == expected


@pytest.mark.parametrize(
    ("purl", "mode"),
    [
        ("pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0", "purl_spec"),
        ("pkg:npm/MyScope/Left-Pad@1.0.0", "purl_spec"),
        ("pkg:gem/Rails@7.0.0", "purl_spec"),
        ("pkg:cpan/AUTHOR/DBI@1.0", "sbom_checker"),
        ("pkg:cpan/AUTHOR/DBI@1.0", "purl_spec"),
        ("pkg:cpan/author/DBI@1.0", "sbom_checker"),
        ("pkg:cpan/author/DBI@1.0", "purl_spec"),
        ("pkg:maven/Org.Apache/Commons-Lang@1.0", "sbom_checker"),
        ("pkg:maven/Org.Apache/Commons-Lang@1.0", "purl_spec"),
        ("pkg:swift/github.com/Alamofire/Alamofire@5.4.3", "sbom_checker"),
        ("pkg:swift/github.com/Alamofire/Alamofire@5.4.3", "purl_spec"),
        ("pkg:git/Owner/Repo@V1", "sbom_checker"),
        ("pkg:git/Owner/Repo@V1", "purl_spec"),
        ("pkg:huggingface/User/Model@V1.0", "sbom_checker"),
        ("pkg:nuget/Newtonsoft.Json@13.0", "sbom_checker"),
        ("pkg:cocoapods/Alamofire@5.0", "sbom_checker"),
        ("pkg:cran/SomePackage@1.0", "sbom_checker"),
        ("pkg:custom/NameSpace/NamePart@V1", "sbom_checker"),
        ("pkg:custom/NameSpace/NamePart@V1", "purl_spec"),
        ("pkg:NPM/left-pad@1.0", "sbom_checker"),
        ("pkg:NPM/left-pad@1.0", "purl_spec"),
        ("not-a-purl", "sbom_checker"),
        ("", "sbom_checker"),
    ],
)
def test_no_change_returns_none(purl, mode):
    assert lowercase_purl(purl, mode) is None


def test_type_is_lowercased_when_another_field_is_rewritten():
    assert (
        lowercase_purl("pkg:NPM/Left-Pad@1.0", "sbom_checker")
        == "pkg:npm/left-pad@1.0"
    )


def test_percent_encoded_uppercase_is_lowercased_and_suffix_is_verbatim():
    assert lowercase_purl(
        "pkg:deb/Ubuntu/OpenSSL%2DThing@3.0?Arch=AMD64#src%2FLib",
        "sbom_checker",
    ) == "pkg:deb/ubuntu/openssl-thing@3.0?Arch=AMD64#src%2FLib"


def test_encoded_slash_stays_encoded_in_name_namespace_and_version():
    assert lowercase_purl(
        "pkg:generic/GitHub.com/Foo%2FBar@1",
        "sbom_checker",
    ) == "pkg:generic/github.com/foo%2Fbar@1"

    assert lowercase_purl(
        "pkg:deb/My%2FOrg/OpenSSL@3.0",
        "sbom_checker",
    ) == "pkg:deb/my%2Forg/openssl@3.0"

    assert lowercase_purl(
        "pkg:oci/Ubuntu@SHA256%2FABC",
        "purl_spec",
    ) == "pkg:oci/ubuntu@sha256%2Fabc"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_purl_case_rules.py -q`

Expected: FAIL with `ModuleNotFoundError: No module named 'purl_resolver.purl_utils.case_rules'`.

- [ ] **Step 3: Implement `src/purl_resolver/purl_utils/case_rules.py`**

Use this implementation:

```python
from __future__ import annotations

from typing import Literal

from packageurl import PackageURL, quote, unquote
from packageurl.validate import DEFINITIONS_BY_TYPE

PurlCaseMode = Literal["sbom_checker", "purl_spec"]

PURL_SPEC_LOWERCASE_NAMESPACE = frozenset({
    "alpm",
    "apk",
    "bitbucket",
    "brew",
    "composer",
    "deb",
    "github",
    "hex",
    "luarocks",
    "qpkg",
    "rpm",
    "vscode-extension",
    "yocto",
})

PURL_SPEC_LOWERCASE_NAME = frozenset({
    "alpm",
    "apk",
    "bitbucket",
    "bitnami",
    "brew",
    "chrome-extension",
    "composer",
    "deb",
    "github",
    "hex",
    "luarocks",
    "oci",
    "otp",
    "pub",
    "pypi",
    "vscode-extension",
})

PURL_SPEC_LOWERCASE_VERSION = frozenset({
    "huggingface",
    "oci",
    "pypi",
    "vscode-extension",
})

_CHECKER_EXTRA_TYPE_FLAGS: dict[str, tuple[bool, bool, bool]] = {
    "bazel": (False, False, True),
    "brew": (False, False, True),
    "chrome-extension": (False, False, True),
    "git": (True, True, True),
    "julia": (False, True, True),
    "opam": (False, True, True),
    "otp": (False, False, True),
    "vcpkg": (False, False, True),
    "vscode-extension": (False, False, False),
    "yocto": (False, True, True),
}


def _checker_type_flags() -> dict[str, tuple[bool, bool, bool]]:
    flags = {
        purl_type: (
            definition.namespace_case_sensitive,
            definition.name_case_sensitive,
            definition.version_case_sensitive,
        )
        for purl_type, definition in DEFINITIONS_BY_TYPE.items()
    }
    flags.update(_CHECKER_EXTRA_TYPE_FLAGS)
    return flags


_CHECKER_TYPE_FLAGS = _checker_type_flags()


def _case_targets(
    purl_type: str, mode: PurlCaseMode
) -> tuple[bool, bool, bool]:
    if mode == "purl_spec":
        return (
            purl_type in PURL_SPEC_LOWERCASE_NAMESPACE,
            purl_type in PURL_SPEC_LOWERCASE_NAME,
            purl_type in PURL_SPEC_LOWERCASE_VERSION,
        )

    flags = _CHECKER_TYPE_FLAGS.get(purl_type)
    if flags is None:
        return False, False, False
    namespace_case_sensitive, name_case_sensitive, version_case_sensitive = flags
    if purl_type == "cpan":
        namespace_case_sensitive = True
    return (
        not namespace_case_sensitive,
        not name_case_sensitive,
        not version_case_sensitive,
    )


def _has_upper(value: str | None) -> bool:
    if not value:
        return False
    decoded = unquote(value)
    return decoded != decoded.lower()


def _lower(value: str) -> str:
    return quote(unquote(value).lower()).replace("/", "%2F")


def _lower_namespace(namespace: str) -> str:
    return "/".join(_lower(segment) for segment in namespace.split("/"))


def _suffix(purl: str) -> str:
    query = purl.find("?")
    fragment = purl.find("#")
    if query != -1 and (fragment == -1 or query < fragment):
        return purl[query:]
    if fragment != -1:
        return purl[fragment:]
    return ""


def lowercase_purl(purl: str, mode: PurlCaseMode) -> str | None:
    try:
        raw = PackageURL.from_string(purl, normalize_purl=False)
    except ValueError:
        return None

    lower_namespace, lower_name, lower_version = _case_targets(raw.type, mode)

    namespace = raw.namespace or None
    new_namespace = namespace
    if namespace and lower_namespace:
        segments = namespace.split("/")
        if any(_has_upper(segment) for segment in segments):
            new_namespace = _lower_namespace(namespace)

    new_name = raw.name
    if lower_name and _has_upper(raw.name):
        new_name = _lower(raw.name)

    new_version = raw.version
    if new_version and lower_version and _has_upper(new_version):
        new_version = _lower(new_version)

    if (
        new_namespace == namespace
        and new_name == raw.name
        and new_version == raw.version
    ):
        return None

    rebuilt = f"pkg:{raw.type}/"
    if new_namespace:
        rebuilt += f"{new_namespace}/"
    rebuilt += new_name
    if new_version:
        rebuilt += f"@{new_version}"
    rebuilt += _suffix(purl)
    return rebuilt
```

Modify `pyproject.toml` line 12 from `"packageurl-python>=0.17.0"` to `"packageurl-python>=0.17.6"`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_purl_case_rules.py -q`

Expected: PASS.

- [ ] **Step 5: Run lint**

Run: `.venv/bin/python -m ruff check src/purl_resolver/purl_utils/case_rules.py tests/test_purl_case_rules.py`

Expected: `All checks passed!`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/purl_resolver/purl_utils/case_rules.py tests/test_purl_case_rules.py
git commit -m "feat: add purl case rules utility"
```

---

### Task 2: Fixer integration

**Files:**
- Modify: `src/purl_resolver/sbom/fixer.py:6-13`, `:66-82`, `:101-111`, `:800-853`
- Modify: `tests/test_sbom_fixer.py:1-150`, and add rule tests after the leaf-rule tests

**Interfaces:**
- Consumes: `PurlCaseMode`, `lowercase_purl(purl, mode)` from Task 1.
- Produces: `ComponentsFixOptions.lowercase_purl: bool`, `ComponentsFixOptions.purl_case_mode: PurlCaseMode`, `RULE_IDS` entry `components.lowercase_purl`, and a `components.lowercase_purl` stats row.

- [ ] **Step 1: Update the existing tests and add failing rule tests**

In `tests/test_sbom_fixer.py`:

- Insert `"components.lowercase_purl"` into `NEW_RULE_IDS` after `"components.remove_leaf_missing_version"` and before `"components.filter_external_references"`.
- In `test_defaults_expose_flat_base_options`, add:
  ```python
  assert o.components.lowercase_purl is True
  assert o.components.purl_case_mode == "sbom_checker"
  ```
- Rename `test_all_enabled_rules_yield_fifteen_stats_in_canonical_order` to `test_all_enabled_rules_yield_sixteen_stats_in_canonical_order`.
- In `test_fix_sbom_copies_input_and_emits_zero_stats_for_enabled_rules`, change `len(result.stats) == 8` to `len(result.stats) == 9`.

Add this helper and tests after the leaf-rule tests:

```python
def _case_options(mode="sbom_checker", enabled=True) -> SbomFixOptions:
    return SbomFixOptions(
        reorder=False,
        set_spec_version=False,
        increment_version=False,
        add_timestamp=False,
        add_manufacturer=False,
        components={
            "lowercase_purl": enabled,
            "purl_case_mode": mode,
            "filter_external_references": False,
            "filter_properties": False,
            "add_provided_by": False,
        },
    )


def test_lowercase_purl_checker_mode_rules_and_stats():
    data = {
        "components": [
            {
                "type": "library",
                "name": "a",
                "purl": "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0",
            },
            {
                "type": "library",
                "name": "b",
                "purl": "pkg:cpan/AUTHOR/DBI@1.0",
            },
            {
                "type": "library",
                "name": "c",
                "purl": "pkg:vscode-extension/Microsoft/VSCode-Python@1.0.0",
            },
        ]
    }
    result = fix_sbom(data, _case_options("sbom_checker"))
    assert result.fixed_sbom["components"][0]["purl"] == (
        "pkg:golang/github.com/masterminds/semver@v3.0.0"
    )
    assert result.fixed_sbom["components"][1]["purl"] == "pkg:cpan/AUTHOR/DBI@1.0"
    assert result.fixed_sbom["components"][2]["purl"] == (
        "pkg:vscode-extension/microsoft/vscode-python@1.0.0"
    )
    assert _stats(result)["components.lowercase_purl"] == 2


def test_lowercase_purl_purl_spec_mode_rules():
    data = {
        "components": [
            {
                "type": "library",
                "name": "a",
                "purl": "pkg:deb/Ubuntu/OpenSSL@3.0?Arch=AMD64#src/Lib",
            },
            {
                "type": "library",
                "name": "b",
                "purl": "pkg:pypi/Django_X@1.0RC1",
            },
            {
                "type": "library",
                "name": "c",
                "purl": "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0",
            },
            {
                "type": "library",
                "name": "d",
                "purl": "pkg:npm/MyScope/Left-Pad@1.0.0",
            },
            {
                "type": "library",
                "name": "e",
                "purl": "pkg:gem/Rails@7.0.0",
            },
        ]
    }
    result = fix_sbom(data, _case_options("purl_spec"))
    assert result.fixed_sbom["components"][0]["purl"] == (
        "pkg:deb/ubuntu/openssl@3.0?Arch=AMD64#src/Lib"
    )
    assert result.fixed_sbom["components"][1]["purl"] == "pkg:pypi/django_x@1.0rc1"
    assert result.fixed_sbom["components"][2]["purl"] == (
        "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0"
    )
    assert result.fixed_sbom["components"][3]["purl"] == (
        "pkg:npm/MyScope/Left-Pad@1.0.0"
    )
    assert result.fixed_sbom["components"][4]["purl"] == "pkg:gem/Rails@7.0.0"
    assert _stats(result)["components.lowercase_purl"] == 2


def test_lowercase_purl_walks_nested_components_but_not_metadata_component():
    data = {
        "metadata": {
            "component": {
                "type": "application",
                "name": "app",
                "purl": "pkg:deb/Ubuntu/Metadata@1.0",
            }
        },
        "components": [
            {
                "type": "library",
                "name": "parent",
                "purl": "pkg:deb/Ubuntu/Parent@1.0",
                "components": [
                    {
                        "type": "library",
                        "name": "child",
                        "purl": "pkg:deb/Ubuntu/Child@1.0",
                    }
                ],
            }
        ],
    }
    result = fix_sbom(data, _case_options("sbom_checker"))
    assert result.fixed_sbom["metadata"]["component"]["purl"] == (
        "pkg:deb/Ubuntu/Metadata@1.0"
    )
    assert result.fixed_sbom["components"][0]["purl"] == "pkg:deb/ubuntu/parent@1.0"
    assert result.fixed_sbom["components"][0]["components"][0]["purl"] == (
        "pkg:deb/ubuntu/child@1.0"
    )
    assert _stats(result)["components.lowercase_purl"] == 2


@pytest.mark.parametrize("purl", [None, "", "not-a-purl"])
def test_lowercase_purl_skips_missing_empty_invalid_and_non_string(purl):
    component = {"type": "library", "name": "a"}
    if purl is not None:
        component["purl"] = purl
    component_non_string = {"type": "library", "name": "b", "purl": 123}
    result = fix_sbom(
        {"components": [component, component_non_string]},
        _case_options("sbom_checker"),
    )
    for item in result.fixed_sbom["components"]:
        assert item.get("purl") in (None, "", "not-a-purl", 123)
    assert _stats(result)["components.lowercase_purl"] == 0


def test_lowercase_purl_is_absent_from_stats_when_disabled():
    data = {"components": [{"purl": "pkg:deb/Ubuntu/OpenSSL@3.0"}]}
    result = fix_sbom(data, _case_options("sbom_checker", enabled=False))
    assert result.fixed_sbom["components"][0]["purl"] == "pkg:deb/Ubuntu/OpenSSL@3.0"
    assert "components.lowercase_purl" not in _stats(result)


def test_lowercase_purl_does_not_mutate_input():
    data = {"components": [{"purl": "pkg:deb/Ubuntu/OpenSSL@3.0"}]}
    before = copy.deepcopy(data)
    fix_sbom(data, _case_options("sbom_checker"))
    assert data == before
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`

Expected: FAIL because `ComponentsFixOptions` has no `lowercase_purl` / `purl_case_mode` and `RULE_IDS` differs.

- [ ] **Step 3: Implement the fixer changes**

In `src/purl_resolver/sbom/fixer.py`:

1. Add imports:
   ```python
   from ..purl_utils.case_rules import PurlCaseMode, lowercase_purl
   ```
2. Insert `"components.lowercase_purl"` into `RULE_IDS` after `"components.remove_leaf_missing_version"`.
3. Add to `ComponentsFixOptions`:
   ```python
   lowercase_purl: bool = True
   purl_case_mode: PurlCaseMode = "sbom_checker"
   ```
4. Add a helper near the component-rule helpers:
   ```python
   def _lowercase_purl(component: dict, mode: PurlCaseMode) -> int:
       purl = component.get("purl")
       if not _is_non_empty_string(purl):
           return 0
       new_purl = lowercase_purl(purl, mode)
       if new_purl is None:
           return 0
       component["purl"] = new_purl
       return 1
   ```
5. In `_apply_components_rules`, read the rule and mode once:
   ```python
   lowercase = _rule_enabled("components.lowercase_purl", options)
   purl_case_mode = options.components.purl_case_mode
   ```
   In the `apply` closure, run it first, before the external-references filter:
   ```python
   if lowercase:
       counts["components.lowercase_purl"] = (
           counts.get("components.lowercase_purl", 0)
           + _lowercase_purl(component, purl_case_mode)
       )
   ```

- [ ] **Step 4: Run the fixer tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_sbom_fixer.py -q`

Expected: PASS. If other tests in the file assert exact stats lists, update them to include `components.lowercase_purl` in the canonical position.

- [ ] **Step 5: Run the full backend test suite**

Run: `.venv/bin/python -m pytest -q`

Expected: PASS. If only e2e network tests fail, run `SKIP_E2E=1 .venv/bin/python -m pytest -q` and expect PASS.

- [ ] **Step 6: Run lint**

Run: `.venv/bin/python -m ruff check src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py`

Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/purl_resolver/sbom/fixer.py tests/test_sbom_fixer.py
git commit -m "feat: add lowercase purl fix rule"
```

---

### Task 3: API and options-store contract coverage

**Files:**
- Modify: `tests/test_sbom_fix_api.py`
- Modify: `tests/test_sbom_fix_options_store.py`

**Interfaces:**
- Consumes: `SbomFixOptions`, `ComponentsFixOptions` from Task 2.
- Produces: no production code; locks the API and persistence contract for the two new fields.

This task is a contract lock: the production code already exists after Task 2, so the new tests should pass immediately. Do not add new production code here.

- [ ] **Step 1: Add the store tests**

In `tests/test_sbom_fix_options_store.py`, add:

```python
def test_save_load_roundtrip_including_purl_case_fields(tmp_path):
    store = SbomFixOptionsStore(tmp_path / "options.json")
    options = SbomFixOptions(
        components=ComponentsFixOptions(
            lowercase_purl=False,
            purl_case_mode="purl_spec",
        )
    )
    store.save(options)
    assert store.load() == options


def test_old_file_without_purl_case_fields_uses_defaults(tmp_path):
    path = tmp_path / "old.json"
    path.write_text(
        '{"components": {"filter_properties": false}}', encoding="utf-8"
    )
    loaded = SbomFixOptionsStore(path).load()
    assert loaded.components.filter_properties is False
    assert loaded.components.lowercase_purl is True
    assert loaded.components.purl_case_mode == "sbom_checker"
```

- [ ] **Step 2: Add the API tests**

In `tests/test_sbom_fix_api.py`, add:

```python
def test_fix_applies_selected_purl_case_mode(client):
    sbom = make_sbom()
    sbom["components"][0]["purl"] = (
        "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0"
    )
    response = upload_fix(
        client,
        sbom,
        options={
            "components": {
                "lowercase_purl": True,
                "purl_case_mode": "sbom_checker",
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["fixed_sbom"]["components"][0]["purl"] == (
        "pkg:golang/github.com/masterminds/semver@v3.0.0"
    )


def test_fix_with_purl_spec_mode_keeps_case_sensitive_golang_purl(client):
    sbom = make_sbom()
    sbom["components"][0]["purl"] = (
        "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0"
    )
    response = upload_fix(
        client,
        sbom,
        options={
            "components": {
                "lowercase_purl": True,
                "purl_case_mode": "purl_spec",
            }
        },
    )
    assert response.status_code == 200
    assert response.json()["fixed_sbom"]["components"][0]["purl"] == (
        "pkg:golang/GitHub.com/Masterminds/Semver@v3.0.0"
    )


def test_options_roundtrip_includes_purl_case_fields(client):
    options = SbomFixOptions(
        components={
            "lowercase_purl": False,
            "purl_case_mode": "purl_spec",
        }
    )
    assert client.post(
        "/api/v1/sbom/fix/options", json={"options": options}
    ).status_code == 200
    body = client.get("/api/v1/sbom/fix/options").json()
    assert body["options"]["components"]["lowercase_purl"] is False
    assert body["options"]["components"]["purl_case_mode"] == "purl_spec"


def test_save_options_rejects_invalid_purl_case_mode(client):
    response = client.post(
        "/api/v1/sbom/fix/options",
        json={"options": {"components": {"purl_case_mode": "bad"}}},
    )
    assert response.status_code == 400
    assert response.json()["error"] == "invalid_options"
```

- [ ] **Step 3: Run the tests**

Run: `.venv/bin/python -m pytest tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py -q`

Expected: PASS. These tests lock the contract already implemented by Task 2; if any fails, fix the Task 2 code before committing.

- [ ] **Step 4: Run lint**

Run: `.venv/bin/python -m ruff check tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py`

Expected: `All checks passed!`

- [ ] **Step 5: Commit**

```bash
git add tests/test_sbom_fix_api.py tests/test_sbom_fix_options_store.py
git commit -m "test: cover purl case option contract"
```

---

### Task 4: Frontend types and rule catalog

**Files:**
- Modify: `frontend/src/types/api.ts:208-217`
- Modify: `frontend/src/views/sbomFixerRules.ts:20`, `:121-304`
- Modify: `frontend/src/views/sbomFixerRules.test.ts:13-68`
- Modify: `frontend/src/views/SbomFixer.vue:417-446`, `:473-503`
- Modify: `frontend/src/i18n/locales/ru.json:118-176`
- Modify: `frontend/src/i18n/locales/en.json:118-176`

**Interfaces:**
- Consumes: nothing from earlier tasks except the agreed option names.
- Produces: `ComponentsFixOptions.lowercase_purl`, `ComponentsFixOptions.purl_case_mode`, `ComponentsRuleKey` excluding `purl_case_mode`, a `COMPONENTS_RULES` entry with id `components.lowercase_purl` and key `lowercase_purl`, page defaults `lowercase_purl: true` / `purl_case_mode: 'sbom_checker'`, and the bilingual rule label, mode labels, and help text.

- [ ] **Step 1: Update the catalog tests first**

In `frontend/src/views/sbomFixerRules.test.ts`:

- Change the components group size from `7` to `8`.
- Change the "covers all 15 rules" test to expect `16` rules and unique ids.
- Change the exact `COMPONENTS_RULES` id list to:
  ```typescript
  expect(COMPONENTS_RULES.map((rule) => rule.id)).toEqual([
    'components.remove_leaf_missing_purl',
    'components.remove_leaf_invalid_purl',
    'components.remove_leaf_missing_version',
    'components.lowercase_purl',
    'components.filter_external_references',
    'components.filter_properties',
    'components.fill_missing_gost_properties',
    'components.add_provided_by',
  ])
  ```
- Add:
  ```typescript
  it('has the purl case rule after the leaf rules', () => {
    const index = COMPONENTS_RULES.findIndex(
      (rule) => rule.id === 'components.lowercase_purl',
    )
    expect(index).toBe(3)
    expect(COMPONENTS_RULES[index].key).toBe('lowercase_purl')
  })
  ```

Run: `npm --prefix frontend run test -- sbomFixerRules`

Expected: FAIL because the rule does not exist and the counts are stale.

- [ ] **Step 2: Add the TypeScript fields and rule entry**

In `frontend/src/types/api.ts`:

```typescript
export interface ComponentsFixOptions {
  remove_leaf_missing_purl: boolean
  remove_leaf_invalid_purl: boolean
  remove_leaf_missing_version: boolean
  lowercase_purl: boolean
  purl_case_mode: 'sbom_checker' | 'purl_spec'
  filter_external_references: boolean
  filter_properties: boolean
  fill_missing_gost_properties: boolean
  add_provided_by: boolean
  provided_by_patterns: ProvidedByPatternItem[]
}
```

Change `ComponentsRuleKey` in `frontend/src/views/sbomFixerRules.ts`:

```typescript
export type ComponentsRuleKey = Exclude<
  keyof ComponentsFixOptions,
  'provided_by_patterns' | 'purl_case_mode'
>
```

Insert the new rule into `COMPONENTS_RULES` after `components.remove_leaf_missing_version`:

```typescript
{
  id: 'components.lowercase_purl',
  key: 'lowercase_purl',
  example: {
    before: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0",
      "purl": "pkg:deb/Ubuntu/OpenSSL@3.0"
    }
  ]
}`,
    after: `{
  "components": [
    {
      "type": "library",
      "name": "openssl",
      "version": "3.0",
      "purl": "pkg:deb/ubuntu/openssl@3.0"
    }
  ]
}`,
  },
},
```

- [ ] **Step 3: Add the rule label, mode labels, and help text**

In `frontend/src/i18n/locales/ru.json`:

- Under `sbomFixer.rules.components`, after `remove_leaf_missing_version`, add:
  ```json
  "lowercase_purl": "Привести PURL к строчному регистру"
  ```
- Under `sbomFixer`, add:
  ```json
  "purlCaseMode": {
    "sbom_checker": "В соответствии с требованиями sbom-checker",
    "purl_spec": "В соответствии с требованиями purl-spec"
  }
  ```
- Under `sbomFixer.help.components`, after `remove_leaf_missing_version`, add a long string with these two blocks (use `\n\n` between blocks and `\n` before each bullet):
  ```text
  Режим «sbom-checker» повторяет правила понижения регистра, которые использует скрипт sbom-checker.py (определения packageurl-python 0.17.6 + 10 типов из sbom_utils.py). Понижаются:
  • namespace — у всех типов, кроме cpan (там требуется верхний регистр), git, huggingface, maven, swid, swift;
  • name — у всех типов, кроме cargo, cocoapods, cpan, cran, git, hackage, huggingface, julia, maven, nuget, opam, rpm, swid, swift, yocto;
  • version — только у vscode-extension.
  Режим может понизить регистр регистрозначимых идентификаторов (например, golang, npm, gem).

  Режим «purl-spec» использует снимок официальной спецификации PURL от 2026-11-07. Понижаются:
  • namespace — у alpm, apk, bitbucket, brew, composer, deb, github, hex, luarocks, qpkg, rpm, vscode-extension, yocto;
  • name — у alpm, apk, bitbucket, bitnami, brew, chrome-extension, composer, deb, github, hex, luarocks, oci, otp, pub, pypi, vscode-extension;
  • version — у huggingface, oci, pypi, vscode-extension.
  Остальные типы не меняются; cpan namespace не меняется.

  В обоих режимах правило обходит всё дерево components[], не трогает metadata.component, пропускает отсутствующие, нестроковые и невалидные PURL, а также неизвестные типы. Меняются только разрешённые поля; qualifiers и subpath сохраняются дословно.
  ```

In `frontend/src/i18n/locales/en.json`, add the mirrored keys and an English translation of the same help text. Keep the type lists identical and use `sbom-checker` / `purl-spec` literally so the help test can find both words.

- [ ] **Step 4: Add the new option defaults to the page**

In `frontend/src/views/SbomFixer.vue`:

- Add to `defaultFixOptions().components`:
  ```typescript
  lowercase_purl: true,
  purl_case_mode: 'sbom_checker',
  ```
- In `applyOptions`, after the components spread, add:
  ```typescript
  options.components.purl_case_mode =
    next.components.purl_case_mode ?? 'sbom_checker'
  options.components.lowercase_purl = next.components.lowercase_purl ?? true
  ```

This keeps the page compiling after the TypeScript interface becomes stricter; the visible selector is added in Task 5.

- [ ] **Step 5: Run the catalog tests to verify they pass**

Run: `npm --prefix frontend run test -- sbomFixerRules`

Expected: PASS.

- [ ] **Step 6: Run the frontend build for TypeScript**

Run: `npm --prefix frontend run build`

Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/types/api.ts frontend/src/views/sbomFixerRules.ts frontend/src/views/sbomFixerRules.test.ts frontend/src/views/SbomFixer.vue frontend/src/i18n/locales/ru.json frontend/src/i18n/locales/en.json
git commit -m "feat: add lowercase purl rule to frontend catalog"
```

---

### Task 5: Frontend selector, help, and i18n

**Files:**
- Modify: `frontend/src/views/SbomFixer.vue:104-140`, `:921+` (styles)
- Modify: `frontend/src/components/RuleHelp.vue` (`.rule-help-description`)
- Modify: `frontend/src/views/SbomFixer.test.ts:12-53` and add tests

**Interfaces:**
- Consumes: Task 4 catalog entry, TypeScript fields, page defaults, and i18n texts.
- Produces: a disabled-aware radio group with `data-purl-case-mode-option` and multi-line help rendering.

- [ ] **Step 1: Update the frontend test fixture and add failing tests**

In `frontend/src/views/SbomFixer.test.ts`, add to the `defaultOptions.components` object:

```typescript
lowercase_purl: true,
purl_case_mode: 'sbom_checker',
```

Add these tests near the other components-group tests:

```typescript
it('defaults the lowercase PURL rule to enabled with sbom_checker mode', async () => {
  const wrapper = await mountFixer()
  expect((wrapper.find(rule('components.lowercase_purl')).element as HTMLInputElement).checked).toBe(true)
  expect(
    (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).checked,
  ).toBe(true)
  expect(
    (wrapper.find('[data-purl-case-mode-option="purl_spec"]').element as HTMLInputElement).checked,
  ).toBe(false)
})

it('disables the PURL case mode selector while the rule is off', async () => {
  const wrapper = await mountFixer()
  await wrapper.find(rule('components.lowercase_purl')).setValue(false)
  expect(
    (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).disabled,
  ).toBe(true)
  expect(
    (wrapper.find('[data-purl-case-mode-option="purl_spec"]').element as HTMLInputElement).disabled,
  ).toBe(true)
})

it('saves the selected PURL case mode and sends it with a fix', async () => {
  const wrapper = await mountFixer()
  await wrapper.find('[data-purl-case-mode-option="purl_spec"]').setValue(true)
  await wrapper.find('.save-settings').trigger('click')
  await flushPromises()
  const saved = saveFixOptionsMock.mock.calls[0][0] as SbomFixOptions
  expect(saved.components.purl_case_mode).toBe('purl_spec')

  const file = await selectFile(wrapper)
  await wrapper.find('.fix-button').trigger('click')
  await flushPromises()
  const sent = fixSbomMock.mock.calls[0][1] as SbomFixOptions
  expect(sent.components.purl_case_mode).toBe('purl_spec')
  expect(fixSbomMock).toHaveBeenCalledWith(file, expect.anything(), [])
})

it('resets the PURL case mode to sbom_checker', async () => {
  const wrapper = await mountFixer()
  await wrapper.find('[data-purl-case-mode-option="purl_spec"]').setValue(true)
  await wrapper.find('.reset-defaults').trigger('click')
  expect(
    (wrapper.find('[data-purl-case-mode-option="sbom_checker"]').element as HTMLInputElement).checked,
  ).toBe(true)
})

it('describes both PURL case modes in the help panel', async () => {
  const wrapper = await mountFixer()
  await wrapper.find('[data-help-for="components.lowercase_purl"]').trigger('click')
  const panel = wrapper.find('[data-rule-row="components.lowercase_purl"] .rule-help-panel')
  expect(panel.text()).toContain('sbom-checker')
  expect(panel.text()).toContain('purl-spec')
})
```

Run: `npm --prefix frontend run test -- SbomFixer`

Expected: FAIL because the selector and markup do not exist.

- [ ] **Step 2: Add the selector**

In `frontend/src/views/SbomFixer.vue`:

- Add a script constant near the other constants:
  ```typescript
  const PURL_CASE_MODES = ['sbom_checker', 'purl_spec'] as const
  ```
- In the `COMPONENTS_RULES` loop, after the `div.rule-row` and before the `provided_by` editor, add:
  ```vue
  <div
    v-if="rule.key === 'lowercase_purl'"
    class="purl-case-mode"
    data-purl-case-mode
  >
    <label
      v-for="mode in PURL_CASE_MODES"
      :key="mode"
      class="purl-case-mode-option"
    >
      <input
        v-model="options.components.purl_case_mode"
        type="radio"
        name="purl-case-mode"
        :value="mode"
        :data-purl-case-mode-option="mode"
        :disabled="!options.components.lowercase_purl"
      />
      <span>{{ t(`sbomFixer.purlCaseMode.${mode}`) }}</span>
    </label>
  </div>
  ```
- Add styles near `.pattern-rows`:
  ```css
  .purl-case-mode {
    flex-basis: 100%;
    display: flex;
    gap: 1rem;
    padding: 0.25rem 0 0.5rem 1.5rem;
  }

  .purl-case-mode-option {
    display: inline-flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 0.9rem;
  }
  ```

- [ ] **Step 3: Add multi-line help support**

In `frontend/src/components/RuleHelp.vue`, add to `.rule-help-description`:

```css
white-space: pre-line;
```

- [ ] **Step 4: Run the frontend tests to verify they pass**

Run: `npm --prefix frontend run test -- SbomFixer`

Expected: PASS. Update any exact saved-options fixture that does not use `cloneOptions()` so it includes the two new fields.

- [ ] **Step 5: Run the full frontend test suite and build**

Run: `npm --prefix frontend run test`

Expected: PASS.

Run: `npm --prefix frontend run build`

Expected: build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/SbomFixer.vue frontend/src/components/RuleHelp.vue frontend/src/views/SbomFixer.test.ts
git commit -m "feat: add purl case mode selector and help"
```

---

### Task 6: Update project specs

**Files:**
- Modify: `specs/domains/sbom-fixing.md`
- Modify: `specs/domains/web-ui.md`
- Modify: `specs/contracts/api-contract.md`
- Modify: `specs/architecture/layers.md`
- Modify: `docs/superpowers/specs/2026-11-07-sbom-fixer-purl-case-design.md` (status only)

**Interfaces:**
- Consumes: the implemented behavior from Tasks 1–5.
- Produces: updated specs that describe 16 rules, the two modes, the selector, the API fields, and the new case-rules module.

- [ ] **Step 1: Load the `vibespec-update` skill**

Use `vibespec-update` and follow its format rules. Read the current specs before editing.

- [ ] **Step 2: Update `specs/domains/sbom-fixing.md`**

- Change every "15 rules" / "15 static rules" reference to 16.
- Add `components.lowercase_purl` to `RULE_IDS` after `components.remove_leaf_missing_version`.
- Add `lowercase_purl: bool = True` and `purl_case_mode: Literal["sbom_checker", "purl_spec"] = "sbom_checker"` to `ComponentsFixOptions`.
- Add the default static row count change from 8 to 9.
- Add a rule-table row for `components.lowercase_purl` with the two modes, the allowed fields, the scope, and the count definition.
- Document the surgical rewrite rule: only permitted `namespace` / `name` / `version` fields change; qualifiers/subpath are preserved verbatim; unknown types and invalid PURLs are skipped; `cpan` namespace is never lowered; type is lowercased only when another permitted field triggers a rewrite.
- Add the rule to the invariants, the API options description, and the help-panel paragraph.
- Add the design doc to the design-rationale list at the top.

- [ ] **Step 3: Update `specs/domains/web-ui.md`**

- Change the catalog count from 15 to 16 and `COMPONENTS_RULES` from 7 to 8.
- Add the new rule to the `components[]` card description and the rule order.
- Document the radio selector, its default `sbom_checker`, its disabled state, and the `data-purl-case-mode` / `data-purl-case-mode-option` test attributes.
- Document the two-block help text and the `RuleHelp.vue` multi-line support.
- Add the new frontend tests to the test inventory.
- Update the defaults sentence to include `lowercase_purl = true` and `purl_case_mode = "sbom_checker"`.

- [ ] **Step 4: Update `specs/contracts/api-contract.md`**

- Add `lowercase_purl` and `purl_case_mode` to every `SbomFixOptions` JSON example.
- Document the defaults, the allowed mode values, the 400 response for an invalid mode, and the fact that an old options file without the keys loads with the defaults.
- Update the options GET/POST description to include the new fields.

- [ ] **Step 5: Update `specs/architecture/layers.md`**

- Change the fixer description from 15 to 16 static rules and mention `components.lowercase_purl`.
- Add `src/purl_resolver/purl_utils/case_rules.py` to the module inventory with its responsibility (mode tables, `lowercase_purl`).
- Update the options persistence description: eight `components.*` flags plus `components.purl_case_mode` and `components.provided_by_patterns`.
- Update any rule-count or components-field-count references.

- [ ] **Step 6: Update the design status**

In `docs/superpowers/specs/2026-11-07-sbom-fixer-purl-case-design.md`, change:

```markdown
Статус: согласовано (2026-11-07)
```

to:

```markdown
Статус: реализовано (2026-11-07)
```

- [ ] **Step 7: Check the specs**

Manually verify that no "15 rules" / "COMPONENTS_RULES with 7" / "8 static rows" references remain in the four files, and that every `SbomFixOptions` example includes the two new fields.

- [ ] **Step 8: Commit**

```bash
git add specs/domains/sbom-fixing.md specs/domains/web-ui.md specs/contracts/api-contract.md specs/architecture/layers.md docs/superpowers/specs/2026-11-07-sbom-fixer-purl-case-design.md
git commit -m "docs: update specs for lowercase purl rule"
```

---

### Task 7: Full verification

**Files:**
- No planned production changes.

**Interfaces:**
- Consumes: all previous tasks.

- [ ] **Step 1: Run backend lint and tests**

Run: `.venv/bin/python -m ruff check src tests`

Expected: `All checks passed!`

Run: `.venv/bin/python -m pytest -q`

Expected: PASS. If only e2e network tests fail, run `SKIP_E2E=1 .venv/bin/python -m pytest -q` and expect PASS.

- [ ] **Step 2: Run frontend tests and build**

Run: `npm --prefix frontend run test`

Expected: PASS.

Run: `npm --prefix frontend run build`

Expected: build succeeds.

- [ ] **Step 3: Verify the worktree**

Run: `git status --short`

Expected: no unexpected modified tracked files. The plan file itself may remain untracked unless you were asked to commit it.

- [ ] **Step 4: Commit only if fixes were needed**

If Step 1 or Step 2 required changes, stage only the files changed by those fixes (never the plan file or unrelated files) and commit them:

```bash
git add <files changed by the verification fixes>
git commit -m "fix: finish lowercase purl verification"
```
