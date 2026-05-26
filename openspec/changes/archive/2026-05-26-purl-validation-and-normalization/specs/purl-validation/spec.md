## ADDED Requirements

### Requirement: Application-level PURL validation
The system SHALL validate PURL format at the application level before any resolver call, using the official `packageurl-python` library.

#### Scenario: Valid PURL passes validation
- **WHEN** a valid PURL string (e.g. `pkg:pypi/requests@2.31.0`) is submitted to the resolve endpoint
- **THEN** the system SHALL successfully parse it without raising a validation error

#### Scenario: Invalid PURL returns error
- **WHEN** a string that does not conform to the PURL specification (e.g. `not-a-purl`) is submitted
- **THEN** the system SHALL return HTTP 400 with `{"error": "invalid_purl", "message": "<description>"}` WITHOUT calling any resolver

#### Scenario: Empty PURL is rejected
- **WHEN** an empty string is submitted
- **THEN** the system SHALL return HTTP 422 (Pydantic validation)

#### Scenario: PURL without namespace is valid
- **WHEN** a valid PURL without namespace (e.g. `pkg:npm/lodash@4.17.21`) is submitted
- **THEN** the system SHALL parse it successfully with `namespace = None`

### Requirement: PURL normalization to cache key form
The system SHALL normalize a valid PURL to `scheme:type/namespace/name` form for use as a cache key. The namespace component SHALL only be included when present in the original PURL.

#### Scenario: PURL with namespace is normalized
- **WHEN** a PURL `pkg:maven/org.apache.commons/io@1.3.4` is parsed
- **THEN** the normalized form SHALL be `pkg:maven/org.apache.commons/io`

#### Scenario: PURL without namespace is normalized
- **WHEN** a PURL `pkg:pypi/requests@2.31.0` is parsed
- **THEN** the normalized form SHALL be `pkg:pypi/requests`

#### Scenario: Version is excluded from normalized form
- **WHEN** a PURL includes version (e.g. `pkg:pypi/requests@2.31.0`)
- **THEN** the normalized form SHALL NOT include the version

#### Scenario: Qualifiers are excluded from normalized form
- **WHEN** a PURL includes qualifiers (e.g. `pkg:deb/debian/curl@7.50.3-1?arch=i386`)
- **THEN** the normalized form SHALL NOT include qualifiers

#### Scenario: Subpath is excluded from normalized form
- **WHEN** a PURL includes a subpath (e.g. `pkg:golang/google.golang.org/genproto#googleapis/api/annotations`)
- **THEN** the normalized form SHALL NOT include the subpath

### Requirement: Original PURL passed to resolvers
The system SHALL pass the original unmodified PURL string to resolvers, preserving all components (version, qualifiers, subpath) for resolver-specific processing.

#### Scenario: Resolver receives full original PURL
- **WHEN** the system calls a resolver with `pkg:pypi/requests@2.31.0`
- **THEN** the resolver SHALL receive the full string `pkg:pypi/requests@2.31.0` including version

#### Scenario: Resolver receives original qualifiers
- **WHEN** the system calls a resolver with `pkg:deb/debian/curl@7.50.3-1?arch=i386`
- **THEN** the resolver SHALL receive the full string including qualifiers

### Requirement: PurlValidationError exception
The system SHALL define a `PurlValidationError` exception class in the `purl_utils` module, distinct from the resolver-specific `InvalidPurlError`.

#### Scenario: PurlValidationError raised on invalid input
- **WHEN** `validate()` is called with an invalid PURL string
- **THEN** a `PurlValidationError` SHALL be raised with a descriptive message

#### Scenario: PurlValidationError propagates to HTTP 400
- **WHEN** `PurlValidationError` is raised during request processing
- **THEN** the system SHALL respond with HTTP 400 and `{"error": "invalid_purl", "message": "<error message>"}`
