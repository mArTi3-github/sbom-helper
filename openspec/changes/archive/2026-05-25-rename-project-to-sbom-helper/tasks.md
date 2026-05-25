## 1. Metadata & Docker config

- [x] 1.1 Rename `pyproject.toml` project name from `purl-resolver` to `sbom-helper`
- [x] 1.2 Rename Docker image (`image: purl-resolver:latest` → `sbom-helper:latest`) and container name (`container_name: purl-resolver` → `sbom-helper`) in `docker-compose.yml`

## 2. Application code

- [x] 2.1 Rename FastAPI title in `src/purl_resolver/main.py` from `"PURL Resolver"` to `"sbom-helper"`
- [x] 2.2 Rename HTML `<title>` and `<h1>` in `src/purl_resolver/templates/index.html` from `"PURL Resolver"` to `"sbom-helper"`

## 3. Documentation & specs

- [x] 3.1 Rename heading in `README.md` from `# PURL Resolver` to `# sbom-helper`
- [x] 3.2 Rename header and project references in `specs/META.md`
- [x] 3.3 Rename project reference in `specs/WORKFLOW.md`
- [x] 3.4 Rename provider description in `specs/contracts/api-contract.md`

## 4. Verification

- [x] 4.1 Run `pytest` to confirm all 5 tests pass
- [x] 4.2 Check that `pip list` shows the package as `sbom-helper`