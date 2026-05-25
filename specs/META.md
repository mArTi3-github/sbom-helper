# sbom-helper — Specification System

This directory contains structured specifications for the sbom-helper project. Specs are optimized for both human developers and AI agents — they provide deterministic context about intended behavior, interfaces, and architectural decisions.

## File Organization

```
specs/
├── META.md                          # This file — rules, templates, glossary
├── INDEX.md                         # Navigation — task-to-spec mapping
├── WORKFLOW.md                      # Development processes and agent workflows
├── architecture/
│   └── layers.md                    # Layer hierarchy, import rules, responsibilities
├── domains/
│   ├── purl-resolution.md           # Core resolution capability
│   └── web-ui.md                    # Browser-based web interface
├── contracts/
│   └── api-contract.md              # HTTP API contract between client and service
└── decisions/
    ├── _template.md                 # ADR template
    └── 0001-purl2repo-as-primary-resolver.md
```

## How to Use

1. **Start with INDEX.md** — find the right spec for your task
2. **Read domain specs** — understand what the system should do
3. **Read architecture specs** — understand constraints and invariants
4. **Read contract specs** — understand interface boundaries
5. **Update specs when behavior changes** — use the templates in this file

## Spec Update Rules

- **Every spec change** must be reflected in INDEX.md (task-to-spec table and directory listing)
- **New domains or contracts** must be added to META.md File Organization section
- **Breaking API changes** must be reflected in the relevant contract spec
- **New architectural constraints** must be added to architecture/layers.md
- **Cross-reference integrity**: all file paths in specs must resolve to existing files

## Templates

### Domain Spec Template

```
# {Domain Name}

## Description
{1-3 sentences about this domain's responsibility}

## Key Files
- `{path}` — {purpose}

## Core Types
{key data structures — code blocks from actual source}

## Flow
{ASCII diagram of the happy path}

## Invariants
- {rule that must always hold}

## Configuration
{relevant config keys and their purpose}
```

### Contract Spec Template

```
# {Contract Name}

## Participants
- **Provider**: {layer/module name}
- **Consumer**: {layer/module name}

## Interface
{interface definitions — code blocks from actual source}

## Initialization
{how things are wired at startup}

## Breaking Change Checklist
- [ ] {condition that would break the contract}
```

### ADR Template

```
# {Title of the decision}

{1-3 sentences: context, decision, rationale}
```
