## ADDED Requirements

### Requirement: Resolve single PURL to repository URL
The system SHALL accept a single PURL string and return the corresponding repository URL with metadata.

#### Scenario: Successful resolution with known PURL
- **WHEN** user submits `POST /api/v1/resolve` with `{"purl": "pkg:pypi/requests@2.31.0"}`
- **THEN** system returns HTTP 200 with `repository_url` containing `https://github.com/psf/requests`, `confidence` containing `"high"`, `evidence` as non-empty array, and `warnings` as array

#### Scenario: Invalid PURL format
- **WHEN** user submits `POST /api/v1/resolve` with `{"purl": "not-a-purl"}`
- **THEN** system returns HTTP 400 with JSON body containing `error` and `message` fields

#### Scenario: Unsupported ecosystem
- **WHEN** user submits `POST /api/v1/resolve` with `{"purl": "pkg:unknown/package@1.0.0"}`
- **THEN** system returns HTTP 400 with JSON body containing `error` and `message` fields

#### Scenario: Valid PURL but no repository found
- **WHEN** user submits `POST /api/v1/resolve` with a valid PURL that purl2repo cannot resolve to any repository
- **THEN** system returns HTTP 200 with `repository_url` set to `null`, `warnings` containing an explanation, and other value fields set to `null` or empty array

#### Scenario: Upstream registry timeout
- **WHEN** purl2repo fails to reach the package registry (network error, timeout)
- **THEN** system returns HTTP 502 with JSON body containing `error` and `message` fields

#### Scenario: Response includes all metadata fields
- **WHEN** user submits `POST /api/v1/resolve` with a resolvable PURL
- **THEN** the response JSON SHALL include all fields: `purl`, `repository_url`, `repository_type`, `repository_kind`, `confidence`, `evidence`, `warnings`, `version_reference`

#### Scenario: Version reference returned when available
- **WHEN** user submits `POST /api/v1/resolve` with a PURL that has a version tag in its repository
- **THEN** `version_reference` SHALL contain a URL pointing to the specific version tree or tag

#### Scenario: Empty purl string rejected
- **WHEN** user submits `POST /api/v1/resolve` with `{"purl": ""}`
- **THEN** system returns HTTP 422 with validation error details

### Requirement: Service health endpoint
The system SHALL provide a health check endpoint for monitoring and container orchestration.

#### Scenario: Health check returns OK
- **WHEN** user submits `GET /health`
- **THEN** system returns HTTP 200 with JSON body indicating service is healthy