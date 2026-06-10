# Specs INDEX

## Task → Spec Mapping

| Task | Spec to Read |
|---|---|---|
| Add a new API endpoint | `contracts/api-contract.md`, `architecture/layers.md` |
| Change the resolution logic | `domains/purl-resolution.md` |
| Modify the web UI | `domains/web-ui.md` |
| Change error handling strategy | `domains/purl-resolution.md`, `contracts/api-contract.md` |
| Add configuration parameter | `domains/purl-resolution.md` |
| Change how purl2repo is called | `architecture/layers.md`, `domains/purl-resolution.md` |
| Add a new layer or module | `architecture/layers.md`, `META.md` |
| Make a breaking API change | `contracts/api-contract.md` (Breaking Change Checklist) |
| Understand the full system | `architecture/layers.md` first, then domain specs |
| Add a fallback resolver | `architecture/layers.md`, `decisions/`, `domains/purl-resolution.md` |
| Change Dockerfile or docker-compose | `architecture/layers.md` |
| Add a new container to docker-compose | `architecture/layers.md` |
| Add or change database integration | `architecture/layers.md`, `domains/purl-resolution.md` |
| Add or modify storage layer | `architecture/layers.md` |
| Add PURL validation or normalization | `domains/purl-resolution.md`, `architecture/layers.md` |
| Enrich CycloneDX SBOM files | `contracts/api-contract.md`, `architecture/layers.md`, `domains/purl-resolution.md`, `domains/web-ui.md` |
| Add batch PURL resolution | `domains/purl-resolution.md`, `architecture/layers.md` |
| Add SBOM file upload UI | `domains/web-ui.md`, `contracts/api-contract.md` |
| Manage database (view, edit, filter, import, export) | `domains/web-ui.md`, `contracts/api-contract.md`, `architecture/layers.md` |
| Refactor CSV import/export or storage interface | `architecture/layers.md`, `contracts/api-contract.md` |
| Add application settings | `domains/purl-resolution.md`, `contracts/api-contract.md`, `architecture/layers.md` |
| Add URL validation for cached URLs | `domains/purl-resolution.md`, `architecture/layers.md` |
| Change resolver error handling | `domains/purl-resolution.md`, `architecture/layers.md` |
| Remove unresolved SBOM components | `contracts/api-contract.md`, `domains/purl-resolution.md`, `domains/web-ui.md` |
| Convert SBOM to images list (container list) | `contracts/api-contract.md`, `domains/web-ui.md`, `architecture/layers.md` |

## Dependency Graph

```
contracts/api-contract.md
        |
        v
domains/purl-resolution.md  ──>  domains/web-ui.md
        |
        v
architecture/layers.md
        |
        v
decisions/0001-purl2repo-as-primary-resolver.md
decisions/0002-postgres-for-resolution-storage.md
decisions/0003-purl-validation-and-normalization.md
decisions/0004-librariesio-as-fallback-resolver.md
decisions/0005-ecosyste-ms-as-fallback-resolver.md
decisions/0006-async-first-resolver-architecture.md
```

The API contract depends on the purl-resolution domain definition. The web UI depends on the API contract. Architecture layers provide the structural constraints for all domains. Decisions document the rationale behind architectural choices.

## Directory Listing

```
specs/
├── META.md                          — Rules, templates, glossary
├── INDEX.md                         — This file
├── WORKFLOW.md                      — Agent workflows
├── architecture/
│   └── layers.md                    — Layer hierarchy and import rules
├── domains/
│   ├── purl-resolution.md           — Core resolution capability
│   └── web-ui.md                    — Browser interface (four pages)
├── contracts/
│   └── api-contract.md              — HTTP API contract (including db-admin and settings endpoints)
└── decisions/
    ├── _template.md                              — ADR template
    ├── 0001-purl2repo-as-primary-resolver.md     — purl2repo as primary resolver
    ├── 0002-postgres-for-resolution-storage.md   — PostgreSQL for resolution caching
    ├── 0003-purl-validation-and-normalization.md — Application-level PURL validation
    ├── 0004-librariesio-as-fallback-resolver.md  — libraries.io as fallback resolver
    ├── 0005-ecosyste-ms-as-fallback-resolver.md  — ecosyste.ms as fallback resolver
    └── 0006-async-first-resolver-architecture.md — Async-first resolver architecture
```