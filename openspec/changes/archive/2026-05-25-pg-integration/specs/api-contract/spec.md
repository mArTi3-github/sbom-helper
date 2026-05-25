## ADDED Requirements

### Requirement: Database connection configuration

The system SHALL support configuration of the PostgreSQL connection via environment variables.

#### Scenario: Configure via DB_URL

- **WHEN** the `DB_URL` environment variable is set
- **THEN** the system SHALL use it as the PostgreSQL connection string
- **WHEN** `DB_URL` is not set
- **THEN** the system SHALL use the default `postgresql://sbom:sbom@localhost:5432/sbom`

## MODIFIED Requirements

### Requirement: POST /api/v1/resolve — DB-aware flow

The response behavior is unchanged, but the internal flow now includes a database lookup step before resolution.

#### Scenario: Repeat request returns cached result

- **WHEN** the same PURL is submitted twice
- **THEN** the second request SHALL return the same `repository_url` without calling purl2repo, and the response SHALL be functionally identical to the first (modulo evidence/warnings)