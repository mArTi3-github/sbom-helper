# ADR-0006: Async-first resolver architecture

## Context

The application's web interface (FastAPI) suffered from event loop blockage during SBOM processing. When a user started SBOM enrichment (which resolves multiple PURLs sequentially through the resolver chain), any other request (Settings page, Database Admin) was blocked until SBOM processing completed.

Root cause: all resolver implementations used synchronous HTTP calls (`httpx.Client`) and synchronous sleep for rate limiting (`time.sleep()`) inside async endpoint handlers, blocking the FastAPI event loop.

## Decision

Convert all resolver implementations to use async I/O:

1. **`Resolver.resolve()`** — changed from `def resolve()` to `async def resolve()`
2. **`Purl2RepoResolver`** — wraps the external synchronous `purl2repo` library in `asyncio.to_thread()`
3. **`EcosystemsResolver`** — replaced `httpx.Client` with `httpx.AsyncClient`
4. **`LibrariesIoResolver`** — replaced `httpx.Client` with `httpx.AsyncClient`; replaced `time.sleep()` with `asyncio.sleep()` for rate limiting
5. **`FakeResolver` (tests)** — updated to async for test compatibility

## Rationale

- FastAPI processes all `async def` endpoints on a single event loop. Synchronous I/O blocks the loop, preventing concurrent request handling.
- `httpx.AsyncClient` and `asyncio.sleep()` yield control back to the event loop during I/O, allowing other requests to proceed.
- `asyncio.to_thread()` offloads the synchronous `purl2repo` library to a thread pool, preventing it from blocking the event loop.
- All three resolvers are independent subsystems with no shared mutable state, making async conversion safe.

## Consequences

- Event loop remains responsive during SBOM processing — parallel requests (Settings, DB Admin) are handled concurrently.
- Rate limiting for libraries.io (1 req/sec) is preserved via `asyncio.sleep()`.
- `purl2repo` calls still occupy a thread pool thread, but the event loop is not blocked.
- Existing tests required minimal changes (async/await + AsyncMock for HTTP client mocks).
- Resolver interface change (`def` → `async def`) is a breaking change for any external code implementing the `Resolver` ABC.