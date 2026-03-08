# Conventional Commits — Extended Reference

Detailed guidance for edge cases and decisions beyond the basics in SKILL.md.

## Choosing the Right Type

### feat vs refactor vs chore

These three are the most commonly confused:

| Scenario                                    | Type       | Reasoning                                   |
| ------------------------------------------- | ---------- | ------------------------------------------- |
| Add a new API endpoint                      | `feat`     | New capability exposed to users/consumers   |
| Rename internal helper for clarity           | `refactor` | No behavior change, no new capability       |
| Move a function to a different module        | `refactor` | Restructuring without behavior change       |
| Add a new dev dependency                    | `chore`    | Tooling change, not a feature or refactor   |
| Update lockfile after dependency bump        | `chore`    | Build/dependency maintenance                |
| Swap out an internal algorithm (same output) | `refactor` | Behavior unchanged from consumer's view     |
| Swap out an internal algorithm (faster)      | `perf`     | Behavior unchanged but measurably faster    |

### fix vs refactor

- `fix` implies something was **broken** and is now corrected
- `refactor` implies the code **worked** but was restructured for clarity, maintainability, or simplicity
- If a refactor happens to fix a latent bug, use `fix` — the outcome matters more than the method

### docs vs chore

- `docs` is for content humans read — READMEs, docstrings, API docs, guides, plans
- `chore` is for config files, ignore patterns, editor settings, CI config
- A `.md` file that documents CI setup is `docs`; the `.yml` pipeline file itself is `ci`

### style vs refactor

- `style` changes are **mechanical** — running a formatter, fixing whitespace, reordering imports
- `refactor` changes require **judgment** — renaming for clarity, extracting functions, simplifying logic
- Rule of thumb: if a tool could make the change automatically, it's `style`

## Breaking Changes

When a commit introduces a breaking change (removed API, changed return type, renamed public function):

```
feat(api)!: replace session tokens with JWT authentication

BREAKING CHANGE: The /auth/token endpoint now returns a JWT instead of
an opaque session token. All clients must update their token handling.
```

- Add `!` after the type/scope
- Include a `BREAKING CHANGE:` footer in the body explaining what broke and what to do
- Breaking changes can apply to any type (`fix!`, `refactor!`, `chore!`)

## Scope Guidelines

### Deriving Scopes

Scopes should map to the project's natural boundaries. Look at:

1. **Top-level directories** — `src/auth/`, `src/api/`, `tests/` suggest scopes like `auth`, `api`, `tests`
2. **Domain concepts** — if the project has users, orders, payments, those make good scopes
3. **Deployment targets** — `lambda`, `frontend`, `worker`, `cli`
4. **Existing commit history** — run `git log --oneline -50` and reuse scopes already in use

### When to Use Scope

- **Use scope** when the type alone doesn't indicate what area changed: `fix(parser): handle escaped quotes`
- **Skip scope** when the change is project-wide or the type is sufficient: `style: apply formatter to all files`
- **Skip scope** for single-file projects or very small codebases

### Scope Consistency

Within a project, use the same scope for the same area. Don't alternate between `auth`, `authentication`, and `login` — pick one and stick with it. Check recent history to match.

## Multi-file Commits

### When to Group

Group files into one commit when they represent a single logical change:

- A function and its tests
- A component and its styles
- A migration and the model it modifies
- A feature flag and the code it gates

### When to Split

Split into separate commits when changes are **independently meaningful**:

- A bug fix and an unrelated formatting cleanup
- A new feature and a dependency upgrade it doesn't need
- Documentation updates for different, unrelated sections

### How to Split

```bash
# Stage only the files for the first logical change
git add src/parser.py tests/test_parser.py
git commit -m "fix(parser): handle nested brackets correctly"

# Then stage the next logical change
git add src/formatter.py
git commit -m "style: apply black formatting to formatter module"
```

## Commit Body Best Practices

Most commits should be single-line. Use a body when:

- The **why** isn't obvious from the summary
- There are **trade-offs** worth documenting
- A **breaking change** needs explanation
- The fix addresses a **subtle bug** that future developers should understand

### Body Format

```
fix(cache): invalidate entries on schema migration

Previously, cached query results would persist across schema migrations,
causing deserialization errors when column types changed. Now the cache
version key includes the schema hash, forcing a cold cache after any
migration runs.
```

- First line is the summary (same rules as single-line commits)
- Blank line separates summary from body
- Body explains **why**, not **what** (the diff shows what)
- Wrap at 72 characters
- Can include bullet points for multiple reasons

## Trailers and Metadata

### Co-authorship

When Claude writes or co-writes the code:

```
Co-Authored-By: Claude <noreply@anthropic.com>
```

When multiple humans collaborate:

```
Co-Authored-By: Name <email@example.com>
```

### Issue References

Reference issues in the summary or body, not as the entire message:

```bash
# Good — descriptive with reference
fix(auth): prevent session fixation on login (#142)

# Bad — reference is the whole message
fix: #142
```

### Closes/Fixes Keywords

Use GitHub/GitLab keywords to auto-close issues:

```
fix(upload): validate file size before processing

Closes #87
```

Valid keywords: `Closes`, `Fixes`, `Resolves` (and lowercase variants).

## Common Mistakes

| Mistake                              | Problem                          | Fix                                          |
| ------------------------------------ | -------------------------------- | -------------------------------------------- |
| `feat: Add new feature`             | Capitalized summary              | `feat: add new feature`                      |
| `fix: fixed the bug.`              | Past tense + trailing period     | `fix: resolve null check on empty input`     |
| `update stuff`                       | No type, vague summary           | `refactor: simplify error handling in parser` |
| `feat: refactor auth and add tests` | Multiple unrelated changes       | Split into `refactor(auth)` + `test(auth)`   |
| `chore: fix bug in login`          | Wrong type                       | `fix(auth): prevent login with expired token` |
| `WIP`                                | Not a meaningful commit message  | Use `git stash` or a draft branch instead    |
| `git commit -m "..." --no-verify`   | Skipping hooks hides real issues | Fix the hook failure, then commit normally   |