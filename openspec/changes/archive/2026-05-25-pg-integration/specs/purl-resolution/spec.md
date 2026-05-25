## MODIFIED Requirements

### Requirement: Resolve single PURL to repository URL

The system SHALL accept a single PURL and return the corresponding repository URL. Before invoking the resolver chain, the system SHALL check PostgreSQL for a cached result.

#### Scenario: PURL found in database

- **WHEN** a PURL is found in `resolved_purls`
- **THEN** the system SHALL return the stored `ResolveResponse` without calling any resolver

#### Scenario: PURL not found, resolved by purl2repo

- **WHEN** a PURL is not found in `resolved_purls` AND purl2repo returns a result with non-null `repository_url`
- **THEN** the system SHALL store the result in `resolved_purls` and return HTTP 200 with the canonical response

#### Scenario: PURL not found, unresolved by purl2repo

- **WHEN** a PURL is not found in `resolved_purls` AND purl2repo returns a result with null `repository_url`
- **THEN** the system SHALL return HTTP 200 with `repository_url: null` and NOT store anything

#### Scenario: PURL not found, error from purl2repo

- **WHEN** a PURL is not found in `resolved_purls` AND purl2repo raises an exception
- **THEN** the system SHALL return the appropriate error response (400 or 502) and NOT store anything