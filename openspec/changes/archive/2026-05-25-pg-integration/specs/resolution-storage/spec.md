## ADDED Requirements

### Requirement: System stores successful resolution results

The system SHALL persist successful resolution results (PURL → repository_url) in PostgreSQL.

#### Scenario: Store after successful resolution

- **WHEN** purl2repo returns a result with non-null `repository_url`
- **THEN** the system SHALL insert a row into `resolved_purls` with all fields from the resolution result

#### Scenario: Skip storage on unresolved PURL

- **WHEN** purl2repo returns a result with null `repository_url`
- **THEN** the system SHALL NOT store the result

#### Scenario: Skip storage on error

- **WHEN** purl2repo raises an exception (InvalidPurlError, UnsupportedEcosystemError, ResolutionError, MetadataFetchError)
- **THEN** the system SHALL NOT store any result

### Requirement: System looks up PURL before calling resolver

The system SHALL query PostgreSQL for an existing stored result before invoking the resolver chain.

#### Scenario: DB cache hit

- **WHEN** a PURL is found in `resolved_purls`
- **THEN** the system SHALL return the stored result without calling purl2repo

#### Scenario: DB cache miss

- **WHEN** a PURL is NOT found in `resolved_purls`
- **THEN** the system SHALL call purl2repo to resolve it

### Requirement: Graceful degradation on database failure

The system SHALL continue to function (without caching) when PostgreSQL is unavailable.

#### Scenario: Database unavailable at lookup

- **WHEN** storage.lookup() fails due to database unavailability
- **THEN** the system SHALL log the error and proceed to call purl2repo directly

#### Scenario: Database unavailable at store

- **WHEN** storage.store() fails due to database unavailability
- **THEN** the system SHALL log the error and return the resolution result without persisting it

### Requirement: Storage layer is resolver-agnostic

The storage module SHALL NOT depend on any specific resolver implementation. It SHALL be usable by any future resolver (purl2repo, purl2src, LLM-based, etc.).

#### Scenario: Store result from any resolver

- **WHEN** any resolver returns a successful result
- **THEN** storage.store() SHALL accept and persist it via the same interface

### Requirement: Database schema is extensible

The `resolved_purls` table SHALL support adding new columns without breaking existing queries.

#### Scenario: Add new column

- **WHEN** a new column is added to `resolved_purls`
- **THEN** existing SELECT and INSERT queries SHALL continue to work (new column has a default value or is nullable)

### Requirement: Table schema defines column types and constraints

The `resolved_purls` table SHALL have the following schema:

| Column | Type | Constraints |
|---|---|---|
| `purl` | `TEXT` | `PRIMARY KEY` |
| `repository_url` | `TEXT` | `NOT NULL` |
| `repository_type` | `TEXT` | nullable |
| `repository_kind` | `TEXT` | nullable |
| `confidence` | `TEXT` | nullable |
| `evidence` | `JSONB` | `DEFAULT '[]'` |
| `warnings` | `JSONB` | `DEFAULT '[]'` |
| `version_reference` | `TEXT` | nullable |
| `resolver` | `TEXT` | `NOT NULL DEFAULT 'purl2repo'` |
| `resolved_at` | `TIMESTAMPTZ` | `NOT NULL DEFAULT NOW()` |

#### Scenario: Create table on startup

- **WHEN** the application starts and PostgreSQL is available
- **THEN** the system SHALL execute `CREATE TABLE IF NOT EXISTS resolved_purls` with the schema above

#### Scenario: Insert full record

- **WHEN** a successful resolution result is stored
- **THEN** all non-nullable columns SHALL be populated and the `purl` SHALL be the primary key (upsert on conflict)

#### Scenario: Extensibility via new columns

- **WHEN** a new column needs to be added in the future
- **THEN** it SHALL be nullable or have a DEFAULT value, ensuring existing queries continue to work