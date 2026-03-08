# Development Standards

This file is auto-loaded every conversation. It defines how Claude should work in this repo.

## Methodology

### TDD — Test-Driven Development

Write the test first. Watch it fail. Write minimal code to pass. No production code without a failing test.
Full process: [.claude/docs/tdd.md](.claude/docs/tdd.md)

### Root Cause Tracing

Never fix at the symptom. Trace backward through the call chain to the original trigger, then fix at the source.
Full process: [.claude/docs/root-cause-tracing.md](.claude/docs/root-cause-tracing.md)

### Subagent-Driven Development

When executing a plan with multiple independent tasks, dispatch a fresh subagent per task with code review between each.
Full process: [.claude/docs/subagent-development.md](.claude/docs/subagent-development.md)

### Parallel Agent Dispatch

When 3+ unrelated failures need investigation, dispatch one agent per independent problem domain concurrently.
Full process: [.claude/docs/parallel-agents.md](.claude/docs/parallel-agents.md)

## Planning

Write implementation plans to `docs/plans/{file_name}.md` before starting non-trivial work. Once a plan has been fully implemented, move it to `docs/plans/archive/`.

## Code Style

- Descriptive variable names (`private_key_bytes` not `pkb`)
- SOLID, DRY, YAGNI — simplicity over complexity
- Type hints on all function signatures
- Numpy-style docstrings for public functions

## Testing

- Run tests: `uv run pytest`
- Run with coverage: `uv run pytest --cov=src --cov-report=term-missing`
- Prefer real code over mocks
- Test fixtures in `tests/fixtures/`

## Skills

Skills live in `.claude/skills/`. Each `SKILL.md` defines an invocable skill with trigger conditions.

### `/code-review`

**Trigger when:** user asks for a "code review", "quality check", pre-commit review, or wants code analyzed for issues.
**Output:** Save markdown report to `docs/code_reviews/{YYYY-MM-DD}_{file_name}.md`.

### `/gitlab-cli`

**Trigger when:** user needs to interact with GitLab — issues, merge requests, MR reviews, CI/CD pipelines, or pushing changes.

### `/github-cli`

**Trigger when:** user needs to interact with GitHub — issues, pull requests, PR reviews, GitHub Actions workflows, or pushing changes.

### `/commit`

**Trigger when:** user asks to commit, make a commit, save work, or when Claude needs to commit changes after completing a task.

### `/readme-generator`

**Trigger when:** user asks to create, generate, update, or improve a README, or says "document this project".
**References:** [.claude/skills/readme-generator/references/](.claude/skills/readme-generator/references/) — analysis methodology, mermaid guidelines, badge reference.

## Project Context

See [.claude/docs/project.md](.claude/docs/project.md) for project-specific details (tech stack, architecture, test markers).
