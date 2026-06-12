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
→ superpowers skills
→ tests
→ implementation
→ ADR/docs update

---

# Project Structure

```text
specs/                          — Architecture specs (INDEX.md — entry point)
  decisions/                    — Architecture Decision Records

src/                            — Source code
```

## Virtual Environment

Dependencies are managed in `.venv/` (Python virtual environment). Always install packages inside `.venv`:

```bash
.venv/bin/pip install <package>
```

Do NOT use `pip install --break-system-packages` or install outside `.venv`. 
Instructions on how to use a virtual environment also should be given to subagents when using a subagent-drivendevelopment approach.

---

# Superpowers Skills (MCP Server)

The `superpowers` MCP server provides 14 skills accessible as tools/prompts:

| Skill | Purpose |
|-------|---------|
| brainstorming | Creative work, design exploration, requirements clarification |
| writing-plans | Small implementation plans with file paths and TDD steps |
| executing-plans | Batch execution with review checkpoints |
| subagent-driven-development | One subagent per task + two-stage code review |
| dispatching-parallel-agents | Distribute independent tasks to concurrent agents |
| test-driven-development | RED-GREEN-REFACTOR cycle |
| systematic-debugging | 4-phase root cause analysis |
| verification-before-completion | Run verification before claiming completion |
| requesting-code-review | Dispatch code review with severity-categorized feedback |
| receiving-code-review | Technical rigor when processing feedback |
| using-git-worktrees | Isolated worktrees for parallel features |
| finishing-a-development-branch | Merge, PR, or cleanup guidance |
| writing-skills | Create/test/deploy new skills |
| using-superpowers | Skill system overview and invocation guide |

Typical workflow with superpowers:

```text
idea
→ brainstorming (explore design)
→ writing-plans (create implementation plan)
→ test-driven-development or subagent-driven-development
→ verification-before-completion
→ requesting-code-review
→ finishing-a-development-branch
```

Use `list_skills` to discover available skills, `recommend_skills` to pick skills for a task, `compose_workflow` to build an ordered workflow from a goal description.

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
→ superpowers brainstorming (explore design, clarify requirements)
→ superpowers writing-plans (implementation plan with file paths and TDD steps)
→ superpowers test-driven-development or subagent-driven-development
→ implementation
→ tests
→ superpowers verification-before-completion
→ ADR/docs update
→ superpowers requesting-code-review
→ superpowers finishing-a-development-branch (merge, PR, or cleanup)

For alternative workflows, use `compose_workflow` from superpowers to generate a tailored sequence.

Планирование изменений (включая описание дизайн-плана) по методологии superpowers ведется в директории docs/superpowers/, как это предусмотрено по умолчанию скиллами superpowers. Папка specs/ описывает документацию проекта в целом, в папке .misc/ находятся различные дополнительные материалы, которые я обрабатываю вручную.