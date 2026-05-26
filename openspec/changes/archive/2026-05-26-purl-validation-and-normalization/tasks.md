## 1. Setup & Dependencies

- [x] 1.1 Add `packageurl-python` to project dependencies

## 2. Create `purl_utils` Module

- [x] 2.1 Create `src/purl_resolver/purl_utils/__init__.py` with public API exports
- [x] 2.2 Define `PurlValidationError` exception class
- [x] 2.3 Define `PurlComponents` dataclass (scheme, type, namespace, name, version, qualifiers, subpath)
- [x] 2.4 Implement `validate(purl: str) -> PurlComponents` — wrap `PackageURL.from_string()`, catch `ValueError`, raise `PurlValidationError`
- [x] 2.5 Implement `normalize(components: PurlComponents) -> str` — build `scheme:type/namespace/name` (namespace only if present)

## 3. Modify Service Layer

- [x] 3.1 Import `validate` and `normalize` from `purl_utils` in `service.py`
- [x] 3.2 Add validation step at the start of `resolve_purl()` — return HTTP 400 on `PurlValidationError`
- [x] 3.3 Replace raw purl string with normalized form for `storage.lookup()` and `storage.store()` calls
- [x] 3.4 Pass original purl string unmodified to resolver

## 4. Update Schemas

- [x] 4.1 Ensure `ResolveResponse.purl` reflects the normalized form (no schema field changes needed — just the value)

## 5. Clear Existing DB Data

- [x] 5.1 Run `TRUNCATE resolved_purls;` on PostgreSQL to remove stale versioned keys

## 6. Update Spec Documents

- [x] 6.1 Update `specs/domains/purl-resolution.md` — add normalized flow diagram, update invariants, add `purl_utils` to Key Files
- [x] 6.2 Update `specs/architecture/layers.md` — add `purl_utils` layer between Service Layer and Storage/Resolver, update import rules
- [x] 6.3 Update `specs/contracts/api-contract.md` — note that `purl` field in response is normalized
- [x] 6.4 Update `specs/META.md` — add `purl_utils` to File Organization
- [x] 6.5 Update `specs/INDEX.md` — add purl validation task-to-spec mapping entry

## 7. Update Tests

- [x] 7.1 Add unit tests for `purl_utils.validate()` and `purl_utils.normalize()`
- [x] 7.2 Update `tests/test_api.py` — verify normalized purl in responses; test that invalid PURL returns 400 without resolver call
- [x] 7.3 Update `tests/test_storage.py` — verify cache roundtrip uses normalized key
