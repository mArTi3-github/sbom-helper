# Spec Workflow

This document defines how AI agents and human developers use and maintain the specification system for the PURL Resolver project. The project's development workflow is defined in `/WORKFLOW.md` at the repository root — this file covers spec-specific processes.

## When to Read Specs

Read the relevant spec before making structural changes:
- Before adding a new endpoint → read `contracts/api-contract.md`
- Before changing resolution behaviour → read `domains/purl-resolution.md`
- Before modifying the web UI → read `domains/web-ui.md`
- Before restructuring modules → read `architecture/layers.md`
- Before changing the API contract → read `contracts/api-contract.md` (Breaking Change Checklist)

## When to Update Specs

Update specs **after** implementation when behaviour has changed:
- **New endpoint or changed response format** → update `contracts/api-contract.md`
- **New configuration parameter** → update the relevant domain spec's Configuration section
- **New layer or changed import rules** → update `architecture/layers.md`
- **New domain** → create `specs/domains/<name>.md`, add to `INDEX.md` and `META.md`

## Workflow for Typical Tasks

### Adding a new API feature

1. Read `contracts/api-contract.md` to understand the existing contract
2. Read `architecture/layers.md` to understand layer responsibilities
3. Read the relevant domain spec (`purl-resolution.md` or `web-ui.md`)
4. Implement the feature
5. Update `contracts/api-contract.md` with new endpoint or response changes
6. Update the domain spec if behaviour or configuration changed

### Changing the resolver strategy

1. Read `architecture/layers.md` to understand the resolver boundary
2. Read `domains/purl-resolution.md` for current resolution flow
3. Read `decisions/0001-purl2repo-as-primary-resolver.md` for original rationale
4. Implement the change
5. Update `architecture/layers.md` if the layer diagram changes
6. Create a new ADR in `decisions/` if the choice is hard to reverse or surprising

## Spec Review Checklist

- [ ] All cross-references point to existing files
- [ ] All "Key Files" paths point to actual source files
- [ ] Invariants are stated affirmatively (not "should not")
- [ ] INDEX.md lists every spec file
- [ ] META.md File Organization section matches actual directory structure
- [ ] No undefined project-specific jargon
- [ ] ASCII diagrams render correctly in monospace