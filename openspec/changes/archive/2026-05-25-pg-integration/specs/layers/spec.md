## MODIFIED Requirements

### Requirement: Layer hierarchy and import rules

The following layer SHALL be added to the architecture:

```
+-----------------------------------------------+
|  Service Layer                                |
|  src/purl_resolver/service.py                 |
|                                               |
|  Orchestrates:                                |
|    storage.lookup() → resolver.resolve() →    |
|    storage.store()                            |
+-----------------------------------------------+

+-----------------------------------------------+
|  Storage Layer                                |
|  src/purl_resolver/storage/                   |
|                                               |
|  interface.py (abstract protocol)             |
|  postgres.py (asyncpg)                        |
|  inmemory.py (dict, for tests)                |
+-----------------------------------------------+
```

#### Scenario: Service Layer calls Storage + Resolver

- **WHEN** `service.resolve_purl()` is called
- **THEN** it SHALL call `storage.lookup(purl)` first, and only call the resolver on cache miss

#### Scenario: Storage Layer is resolver-agnostic

- **WHEN** storage methods are called
- **THEN** they SHALL NOT import or reference any resolver module

#### Scenario: API Layer calls Service Layer

- **WHEN** `router.py` receives a POST /api/v1/resolve request
- **THEN** it SHALL call `service.resolve_purl()`, not purl2repo directly

### Requirement: Import rules

- API Layer imports Service Layer (`service.py`) — but not vice versa
- Service Layer imports Storage Layer (`storage/interface.py`) and resolvers (`purl2repo`)
- Storage Layer is a standalone module — no internal project imports from outside `storage/`