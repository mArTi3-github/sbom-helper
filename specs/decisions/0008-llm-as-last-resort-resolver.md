# ADR-0008: LLM as last-resort resolver

## Context

Deterministic resolvers (purl2repo, deps.dev, ecosyste.ms, libraries.io, apk) leave a long tail of packages without a resolvable repository URL. An LLM with web-search capabilities can find repositories for such packages, but is expensive, non-deterministic, and requires an external API key.

## Decision

Add `LlmResolver` as the last resolver in the chain, enabled only when the user provides an OpenAI-compatible endpoint configuration:
- Settings: `llm_resolver_enabled` (default `false`), `llm_resolver_base_url`, `llm_resolver_api_key`, `llm_resolver_model`, `llm_resolver_attempts_count` (default 2), `llm_resolver_timeout` (default 60 s)
- The LLM is prompted to return a single JSON object (`purl`, `status`, `repository_url`); the response is validated against this schema
- Every returned URL is verified with an HTTP HEAD request before being accepted; failed checks are fed back into the prompt for the next attempt
- If any required configuration is missing, the resolver is omitted from the chain with a warning

## Rationale

- Placed last so the LLM is called only when all cheaper, deterministic resolvers fail
- JSON schema validation plus the HEAD check prevent hallucinated or broken URLs from entering the database
- OpenAI-compatible API keeps the integration vendor-neutral

## Consequences

- Long-tail PURLs may now resolve when an LLM endpoint is configured
- Per-PURL latency increases when the LLM is reached (multiple attempts with a configurable timeout)
- Resolver name `"llm"` stored in DB results distinguishes the resolution source
- Requires external credentials — the feature is opt-in and disabled by default
