# ADR-0008: LLM as last-resort resolver

## Context

Deterministic resolvers (purl2repo, deps.dev, ecosyste.ms, libraries.io, apk) leave a long tail of packages without a resolvable repository URL. An LLM with web-search capabilities can find repositories for such packages, but is expensive, non-deterministic, and requires an external API key.

## Decision

Add `LlmResolver` as the last resolver in the chain, enabled only when the user provides an OpenAI-compatible endpoint configuration:
- Settings: `llm_resolver_enabled` (default `false`), `llm_resolver_base_url`, `llm_resolver_api_key`, `llm_resolver_model`, `llm_resolver_attempts_count` (default 2), `llm_resolver_timeout` (default 60 s), `llm_resolver_verify_ssl` (default `true`), `llm_resolver_ca_bundle` (path to a PEM CA bundle, empty by default), `llm_resolver_max_tool_rounds` (default 3, range 1–10)
- Every chat completion passes OpenAI tool definitions: `web_search` (query) and `web_fetch` (url). The model may call them repeatedly; `LlmResolver` executes each call on the sbom-helper host and feeds the result back until the model returns a final answer or the round limit is reached
- `web_search` queries a locally deployed SearXNG instance supplied as a compose service (`searxng`, no published port) at `SEARXNG_URL` (default `http://searxng:8080`), using its JSON API and returning the top 5 results
- `web_fetch` fetches `http(s)` pages only, blocks private/loopback/link-local/reserved/multicast/unspecified addresses by resolving every host, re-checks each redirect hop (at most 3), caps the body at 512 KiB, and uses a dedicated client with default TLS verification
- Exhausting `llm_resolver_max_tool_rounds` is terminal for that PURL: `resolve()` does not run further `attempts_count` attempts
- The LLM is prompted to return a single JSON object (`purl`, `status`, `repository_url`); the response is validated against this schema
- Every returned URL is verified with an HTTP HEAD request before being accepted; failed checks are fed back into the prompt for the next attempt
- If any required configuration is missing, the resolver is omitted from the chain with a warning

## Rationale

- Placed last so the LLM is called only when all cheaper, deterministic resolvers fail
- JSON schema validation plus the HEAD check prevent hallucinated or broken URLs from entering the database
- OpenAI-compatible API keeps the integration vendor-neutral

## Consequences

- Long-tail PURLs may now resolve when an LLM endpoint is configured, using real web search instead of the model's memory
- Search is performed from the sbom-helper host through a locally deployed SearXNG instance, so no external search API key is required
- SearXNG becomes a runtime dependency of the compose deployment: it ships as a separate compose service with no published port, and its `SEARXNG_SECRET` is auto-generated into `.env` by `scripts/update.sh` (or set manually). When the app runs outside compose (bare `.venv`), `web_search` returns an error to the model and resolution degrades to the model's own knowledge instead of failing
- Per-PURL latency increases when the LLM is reached: tool-calling rounds are bounded by `llm_resolver_max_tool_rounds` (at most `max_tool_rounds + 1` model calls per attempt), and exhausting the limit stops further attempts
- `web_fetch` is an SSRF-sensitive capability: it accepts only `http(s)`, blocks private/reserved destination IPs on every redirect hop, and caps response size and time; fetched page content is untrusted, so acceptance still depends on the JSON schema check and the HEAD verification
- `web_fetch` uses a separate HTTP client with default TLS verification; `llm_resolver_verify_ssl` and `llm_resolver_ca_bundle` keep applying to the LLM endpoint only
- Resolver name `"llm"` stored in DB results distinguishes the resolution source
- Requires external credentials for the LLM endpoint — the feature is opt-in and disabled by default
- Outbound TLS trust for the LLM endpoint is configurable: `llm_resolver_ca_bundle` trusts a corporate CA (recommended); `llm_resolver_verify_ssl=false` disables verification as a temporary fallback
