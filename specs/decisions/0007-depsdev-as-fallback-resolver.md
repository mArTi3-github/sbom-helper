# ADR-0007: deps.dev as fallback resolver

## Context

purl2repo does not support all ecosystems, and ecosyste.ms/libraries.io coverage depends on third-party registry metadata. deps.dev (Google) exposes a free, API-key-free v3 API with deterministic source repository links (e.g. the `<scm>` element of Maven POMs) for Maven, npm, Go, PyPI, NuGet, Cargo, and RubyGems packages.

## Decision

Add `DepsdevResolver` as the second resolver in the chain, immediately after purl2repo, for PURL types supported by deps.dev. It is:
- Enabled by default (`depsdev_enabled`, no API key required)
- Rate-limited (~1 request/second) and uses the shared retry configuration
- Uses the package version when present; for unversioned PURLs it falls back to the default (or latest) published version
- Returns the repository URL normalized to an HTTPS form (strips `scm:git:` prefixes, converts `git://`/`ssh://` to `https://`, drops `/tree/...` segments and trailing `.git`)
- Degrades gracefully — API errors, unsupported types, and missing links produce warnings, not failures

## Rationale

- Deterministic source: the Maven `<scm>` link is published by the project itself, not inferred
- Free and simple — no API key, no registry accounts
- Placed early in the chain because it is cheap and reliable for its supported types

## Consequences

- Resolver chain order: purl2repo → deps.dev → ecosyste.ms → libraries.io → apk → llm
- Resolver name `"depsdev"` stored in DB results distinguishes the resolution source
- Only the seven supported types can be resolved; other types fall through to the next resolver
