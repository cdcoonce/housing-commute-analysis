---
name: commit
description: >
  Git commit workflow with enforced conventional commit style. Use when Claude
  needs to stage and commit changes, craft commit messages, or the user asks to
  commit, make a commit, or save their work. Ensures consistent commit message
  format, proper scoping, and atomic commits across the project.
---

# Commit Skill

Stage and commit changes following conventional commit style and atomic commit principles.

## Commit Message Format

```
<type>(<optional scope>): <short summary>
```

- **Lowercase** everything — type, scope, and summary
- **No period** at the end of the summary
- **Imperative mood** — "add feature" not "added feature" or "adds feature"
- **50 characters max** for the summary line (soft limit, 72 hard limit)
- Summary describes the **why**, not the what (the diff shows the what)

### Types

| Type       | When to use                                              | Example                                       |
| ---------- | -------------------------------------------------------- | --------------------------------------------- |
| `feat`     | New feature or capability                                | `feat: add user authentication flow`          |
| `fix`      | Bug fix                                                  | `fix: resolve null pointer on empty input`    |
| `refactor` | Code change that neither fixes a bug nor adds a feature  | `refactor: extract parser into standalone module` |
| `style`    | Formatting, whitespace, semicolons — no logic change     | `style: apply formatter to config files`      |
| `docs`     | Documentation only                                       | `docs: add API usage examples to readme`      |
| `test`     | Adding or updating tests                                 | `test: add edge case coverage for validator`  |
| `chore`    | Build process, tooling, dependencies, config             | `chore: update dependency lockfile`           |
| `perf`     | Performance improvement                                  | `perf: cache repeated database lookups`       |
| `ci`       | CI/CD pipeline changes                                   | `ci: add lint step to PR workflow`            |

### Scope (Optional)

Use scope to narrow context when the type alone is ambiguous. Derive scopes from the project's directory structure or domain areas:

```
feat(auth): add OAuth2 token refresh
fix(api): handle timeout on large payloads
docs(contributing): add setup instructions
```

## Workflow

1. **Review changes** — Run `git status` and `git diff` (staged + unstaged) to understand what changed
2. **Check recent history** — Run `git log --oneline -10` to match the project's existing commit style
3. **Verify intent** — Confirm the changes form a single logical unit; if not, suggest splitting into multiple commits
4. **Stage files** — Add specific files by name (`git add file1 file2`), never `git add -A` or `git add .`
5. **Craft message** — Select the correct type, add scope if helpful, write an imperative summary
6. **Commit** — Use a heredoc for the message to ensure clean formatting
7. **Verify** — Run `git status` after to confirm the commit succeeded

### Multi-line Commits

For commits that need a body (rare — prefer concise single-line messages):

```
<type>(<scope>): <summary>

<body explaining why, not what>
```

- Blank line between summary and body
- Body wraps at 72 characters
- Use body only when the summary alone can't convey the reasoning

## Rules

- **Atomic commits** — One logical change per commit. A feature and its tests can be one commit. An unrelated formatting fix should be a separate commit.
- **No secrets** — Never commit `.env`, credentials, API keys, or tokens. Warn the user if these are staged.
- **No generated artifacts** — Don't commit build output, dependency directories, or compiled files. Check `.gitignore` coverage before staging.
- **New commits only** — Always create a new commit. Never amend unless the user explicitly asks.
- **No skipping hooks** — Never use `--no-verify`. If a hook fails, fix the underlying issue.
- **Co-author line** — Append the co-author trailer when Claude authored or co-authored the changes:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

## Examples

```bash
# Feature — new capability
feat: add webhook notification system

# Feature with scope
feat(api): add rate limiting middleware

# Fix — bug correction
fix: prevent crash on malformed JSON input

# Style — formatting only
style: apply consistent indentation across modules

# Docs — documentation
docs: add architecture decision records

# Chore — tooling/config
chore: broaden gitignore to cover build artifacts

# Test with scope
test(auth): add integration tests for token refresh

# Refactor with scope
refactor(db): replace raw queries with query builder
```

## Reference Documentation

- [conventional-commits.md](references/conventional-commits.md) — type selection guide, breaking changes, scope strategies, multi-file commit decisions, body formatting, trailers, and common mistakes
