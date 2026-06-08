# ADR-0002: PostgreSQL for resolution result storage

## Context

Phase 2 requires persisting successful PURL → repository URL resolution results so that subsequent lookups of the same PURL can be served without calling a remote resolver. The application currently has no database — only a file-based cache inside purl2repo that caches registry HTTP responses, not resolution results.

## Decision

Use **PostgreSQL** as the storage backend via the **asyncpg** driver, accessed through a thin `storage/` abstraction layer (interface + `PostgresCache` implementation). Redis was considered as a simpler cache but was rejected because the data needs to survive container restarts. An ORM (SQLAlchemy) was explicitly avoided for the initial implementation — a single table with two query patterns (`SELECT` and `INSERT`) does not justify the dependency.

## Consequences

- Storage survives restarts (unlike Redis without persistence, or in-memory dict)
- Graceful degradation: if PostgreSQL is unavailable, the resolver still works (without caching)
- Adding a future multi-resolver architecture is straightforward — `storage/` is resolver-agnostic
- Schema changes require manual migration tooling later; `CREATE TABLE IF NOT EXISTS` + `schema.sql` suffice for now
- Operational cost of running a PostgreSQL container is accepted in exchange for data durability