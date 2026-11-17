# ADR-0009: Source archive links for PURL versions

## Status

Accepted

## Context

The PURL resolver returns a repository URL for a component but not a link to the source archive of the exact version named in the PURL. SBOM checks and an external API consumer need a downloadable source archive for that version. GitHub exposes archives by tag and by commit:

- `https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.tar.gz`
- `https://github.com/{owner}/{repo}/archive/{sha}.tar.gz`

Tag naming varies per repository (`v23.8.16.40-lts`, `rel_23_8_16_40`, `release-1.2.3`), so matching the PURL version to a tag is a separate deterministic task. The existing `resolved_purls` cache is keyed by a versionless PURL, and repository resolution must keep its current contract and cache semantics.

## Decision

Add a source archive lookup mode to `POST /api/v1/resolve/batch` (`find_source_archive`, `force_refresh`) backed by a separate component set:

1. **Separate storage.** Store archive results in the new `purl_source_archives` table keyed by the canonical PURL **with** version (qualifiers and subpath removed). `SourceArchiveStorage` is a separate ABC from `Storage`, with `PostgresSourceArchiveStorage` and an in-memory fallback. `resolved_purls` is unchanged.
2. **Tags from git.** Retrieve tag names and commit SHAs with `git ls-remote --tags <repository_url>`, including peeled `^{}` refs, with prompt suppression (`GIT_TERMINAL_PROMPT=0`, `GIT_ASKPASS=/bin/true`), the `source_archive_timeout` timeout, and output/tag-count limits. No GitHub REST API and no GitHub token.
3. **Deterministic matching in v1.** Extract the longest numeric chain from tag names and PURL versions, ignore prefixes, normalize suffixes, compare numeric tuples with zero padding, and classify:
   - `exact` — equal tuples and, when the PURL version has a suffix, an equal suffix;
   - `near` — nearest tag in the same `major.minor`, preferring an equal tuple, then the highest version below the target, then the lowest above;
   - otherwise no archive link.
   No LLM participates in tag selection.
4. **GitHub-only first version.** Only `github.com`/`www.github.com` repositories with a strict `/{owner}/{repo}` path produce archive links. Other hosts return `repository_only` with `unsupported_host`. The package boundary leaves room for more hosts.
5. **Negative caching.** Cache all four persistent outcomes (`exact`, `near`, `repository_only`, `not_found`) in `purl_source_archives`. `no_version` and `non_numeric_version` are API-only results and are not persisted. `force_refresh` bypasses only the archive cache, not the versionless repository cache.
6. **Verified URLs.** Construct archive URLs from validated owner/repo and tag or 40-hex SHA, then verify them with a redirected HEAD request (`follow_redirects=True`, final status below 400). Unverified URLs are stored only as `repository_only` / `archive_check_failed`.

## Rationale

- A separate table preserves every existing `resolved_purls` invariant: one versionless row per PURL, `ON CONFLICT (purl)`, the four-column schema, CSV import/export, and DB admin behavior. A versioned PURL column in `resolved_purls` would mix two record kinds in one table and break those contracts.
- `git ls-remote --tags` needs no token and has no GitHub API rate limit (the anonymous GitHub API limit is 60 requests/hour, and GitHub token support was removed from the project). It also works for non-GitHub git hosts, keeping host support extensible.
- Deterministic matching is reproducible and cheap, and it covers the observed tag conventions (prefixes, suffixes, separators, pre-releases). An LLM cannot add a verified match where the deterministic rules find none, because any selected tag must still pass the same `git ls-remote` and version checks; it would only choose between equally exact tags. It is therefore excluded from v1.
- Negative caching avoids repeated git and HEAD calls for PURLs that will not match, which matters for batch API consumers.
- HEAD verification prevents storing fabricated or broken links and rejects tags that do not actually produce an archive.

## Alternatives Considered

- **Extend `resolved_purls` with nullable archive columns.** Fewer modules, but one versionless row would have to hold many versions; versioned rows would share the table with normal resolutions and leak into `ON CONFLICT (purl)`, DB admin, and CSV export.
- **Key by `(repository_url, version)`.** Logically exact, but requires stable repository URL normalization (redirects, `.git`, scheme) and a guaranteed repository before storage; invalidation and lookup are more complex.
- **GitHub REST API `/tags`.** Rate-limited (60 requests/hour anonymously) and requires a token the project no longer supports.
- **LLM-only or deterministic-then-LLM matching.** Non-reproducible and costly; with mandatory tag verification the LLM adds no matches, only tie-breaking that deterministic priority already handles.
- **Direct source archive enrichment in SBOM files.** Out of scope for v1; archive links are exposed through the resolver API and UI only.

## Consequences

- A new table, storage surface, batch API fields, UI mode, settings, and a second backup file are added; the existing batch response shape and `resolved_purls` semantics remain compatible.
- Responses carry an explicit `match_type`, so a near or repository-only result cannot be mistaken for an exact archive link.
- Archive lookups are synchronous per batch and can be slow on large batches; `source_archive_concurrency` bounds parallelism and consumers should send smaller archive-mode batches. TTL refresh and background archive jobs are deliberately absent in v1.
- Non-GitHub hosts and any tag scheme outside the deterministic rules return `repository_only`, so coverage is intentionally narrower than repository resolution.
- Archive warnings (for example multiple exact tags) are runtime-only; cache hits return them empty because warnings are not persisted.
- Restoring a backup keeps existing `purl_source_archives` rows in merge mode and only overwrites them with `--mode replace`.
