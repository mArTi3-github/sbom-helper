## MODIFIED Requirements

### Requirement: Resolve PURL to repository URL
The system accepts a single Package URL (PURL) string and returns the corresponding source code repository URL with confidence, evidence, and metadata. The PURL is validated and normalized at the application level before any resolver call. Normalized PURL (`scheme:type/namespace/name`) is used as the cache key and returned in the response. The original PURL string is passed to resolvers for their own processing.

#### Scenario: Successful resolution with version
- **WHEN** a request with `{"purl": "pkg:pypi/requests@2.31.0"}` is submitted
- **THEN** the response SHALL have HTTP 200 with `purl` containing the normalized form `pkg:pypi/requests` and `repository_url` containing the resolved repository URL

#### Scenario: Cache hit with normalized key
- **WHEN** a PURL `pkg:pypi/requests@2.31.0` is resolved and cached, then a second request for `pkg:pypi/requests@3.0.0` is submitted
- **THEN** the second request SHALL hit the cache (since both normalize to `pkg:pypi/requests`) without calling any resolver

#### Scenario: Cache miss with different package
- **WHEN** `pkg:pypi/requests@2.31.0` is cached and a request for `pkg:pypi/flask@2.0.0` is submitted
- **THEN** the system SHALL call the resolver (different normalized key `pkg:pypi/flask`)

#### Scenario: Invalid PURL rejected early
- **WHEN** a request with an invalid PURL string (e.g. `not-a-purl`) is submitted
- **THEN** the system SHALL return HTTP 400 WITHOUT calling any resolver or storage

#### Scenario: Response contains normalized purl
- **WHEN** a request with `pkg:pypi/requests@2.31.0` succeeds
- **THEN** the response `purl` field SHALL be `pkg:pypi/requests` (not the original versioned form)

#### Scenario: Storage stores normalized key
- **WHEN** a resolution result is stored
- **THEN** the `purl` used as the primary key in storage SHALL be the normalized form

#### Scenario: Unresolved PURL not stored
- **WHEN** no resolver finds a repository URL
- **THEN** the result SHALL NOT be stored (unchanged behavior)

#### Scenario: Validation error before cache lookup
- **WHEN** an invalid PURL is submitted
- **THEN** the system SHALL NOT perform a storage lookup or resolver call
