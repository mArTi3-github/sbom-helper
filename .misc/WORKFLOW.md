# WORKFLOW.md

## Core Principles

- Keep specs lightweight.
- Prefer small vertical slices over large implementations.
- Avoid overengineering.
- Evolve architecture incrementally.
- Use AI to generate drafts, not final decisions.

---

# High-Level Workflow

idea
→ grill-with-docs
→ OpenSpec proposal/tasks
→ tests
→ implementation
→ ADR/docs update

---

# Project Structure

```text
specs/                          — Architecture specs (INDEX.md — entry point)
docs/
  adr/                          — Architecture Decision Records only

openspec/
  changes/
    archive/                    — Completed change archives

src/                            — Source code

.misc/
  plans/                        — Design plans (may be already implemented)
```

## Virtual Environment

Dependencies are managed in `.venv/` (Python virtual environment). Always install packages inside `.venv`:

```bash
.venv/bin/pip install <package>
```

Do NOT use `pip install --break-system-packages` or install outside `.venv`.

---

# Development Process

## 1. Start From Idea

Input:
- `idea.txt`
- feature idea
- architecture idea

Do NOT start coding immediately.

---

## 2. Use grill-with-docs

Use grill-with-docs BEFORE implementation for:
- requirement clarification
- MVP boundaries
- architecture risks
- edge cases
- hidden assumptions

Typical prompt:

```text
Use grill-with-docs to analyze this feature.
Focus on:
- unclear requirements
- technical risks
- MVP scope
- architecture implications
```

---

## 3. Save Discussion Results

After grill-with-docs:

Generate:
- discussion summary
- requirements
- constraints
- decisions
- unresolved questions

Do NOT rely on chat history.

Persist important information in repository files.

---

# OpenSpec Workflow

## 4. Create Small OpenSpec Changes

Do NOT create specs for the entire application.

Create specs per capability/subsystem.

Good:
- CSV import
- authentication
- portfolio analysis

Bad:
- complete backend architecture

---

## 5. Generate OpenSpec Artifacts

Use AI to generate:
- `proposal.md`
- `tasks.md`
- `design.md` (only if needed)
- ADR drafts

Human reviews and adjusts them.

---

## 6. Keep Tasks Small

Tasks should be:
- vertical
- user-visible
- independently testable

Good:
- validate malformed CSV rows
- persist uploaded portfolios

Bad:
- implement backend
- create frontend

---

# Design Documents

Create `design.md` ONLY when:
- architecture decisions exist
- major tradeoffs exist
- subsystem complexity is high

Do NOT create design docs for trivial features.

---

# ADR Rules

Create ADRs for:
- database choices
- auth strategy
- realtime architecture
- major framework decisions

Keep ADRs short.

Template:

```md
# Decision

# Rationale

# Consequences
```

---

# TDD-lite Workflow

For each task:

task
→ implementation
→ tests
→ run tests
→ refactor

Tests can be written after implementation (as in this session) or before (preferred for new modules).

---

# Testing Strategy

Use:
- pytest for unit and integration tests
- pytest-asyncio for async tests
- TestClient (FastAPI/httpx) for API integration tests
- testcontainers[postgres] for database e2e tests

Prefer:
- integration tests
- minimal mocks
- real workflows
- `tests/test_<module>.py` naming convention

Avoid:
- excessive unit testing
- snapshot-heavy tests
- over-mocking

Run tests from project root:
```bash
.venv/bin/pytest tests/ -v
```

---

# AI Usage Rules

AI SHOULD:
- generate drafts
- generate specs
- generate tests
- generate implementation plans
- generate boilerplate

Human SHOULD:
- define scope
- approve architecture
- review tradeoffs
- prevent overengineering

---

# Important Rules

## DO

- Keep specs small.
- Keep architecture evolving.
- Review AI-generated tasks.
- Use incremental refinement.
- Persist important decisions.

## DO NOT

- Generate giant upfront architecture.
- Create enterprise complexity for MVP.
- Implement huge features in one step.
- Rely only on chat memory.
- Let AI define product scope alone.

---

# Recommended Daily Workflow

feature idea
→ grill-with-docs
→ discussion summary → persist to `.misc/plans/`
→ OpenSpec proposal/tasks
→ implementation
→ tests
→ ADR/docs update
→ archive OpenSpec change

---

# Scaling Strategy

Early stage:
- lightweight OpenSpec
- minimal docs
- rapid iteration

Later:
- more ADRs
- richer design docs
- stronger architecture discipline

Avoid premature process complexity.
