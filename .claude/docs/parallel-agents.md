# Dispatching Parallel Agents

When you have multiple unrelated failures (different test files, different subsystems, different bugs), investigating them sequentially wastes time. Each investigation is independent and can happen in parallel.

**Core principle:** Dispatch one agent per independent problem domain. Let them work concurrently.

## When to Use

**Use when:**

- 3+ test files failing with different root causes
- Multiple subsystems broken independently
- Each problem can be understood without context from others
- No shared state between investigations

**Don't use when:**

- Failures are related (fix one might fix others)
- Need to understand full system state
- Agents would interfere with each other

## The Pattern

### 1. Identify Independent Domains

Group failures by what's broken:

- File A tests: Data validation logic
- File B tests: API response handling
- File C tests: Database connection pooling

Each domain is independent—fixing validation doesn't affect connection pooling.

### 2. Create Focused Agent Tasks

Each agent gets:

- **Specific scope:** One test file or subsystem
- **Clear goal:** Make these tests pass
- **Constraints:** Don't change other code
- **Expected output:** Summary of what you found and fixed

### 3. Dispatch in Parallel

```python
# In Claude Code environment
Task("Fix tests/test_validation.py failures")
Task("Fix tests/test_api_responses.py failures")
Task("Fix tests/test_db_pool.py failures")
# All three run concurrently
```

### 4. Review and Integrate

When agents return:

- Read each summary
- Verify fixes don't conflict
- Run full test suite: `uv run pytest`
- Integrate all changes

## Agent Prompt Structure

Good agent prompts are:

1. **Focused** - One clear problem domain
2. **Self-contained** - All context needed to understand the problem
3. **Specific about output** - What should the agent return?

```markdown
Fix the 3 failing tests in tests/test_data_validation.py:

1. "test_validates_empty_dataframe" - expects ValueError, gets None
2. "test_validates_column_types" - type mismatch on numeric columns
3. "test_validates_date_range" - date parsing fails on edge cases

Your task:

1. Read the test file and understand what each test verifies
2. Identify root cause - logic error or test expectation issue?
3. Fix by:
   - Correcting validation logic if buggy
   - Adjusting test expectations if testing changed behavior

Do NOT just increase timeouts or add workarounds - find the real issue.

Return: Summary of what you found and what you fixed.
```

## Common Mistakes

| Mistake                                    | Fix                                                  |
| ------------------------------------------ | ---------------------------------------------------- |
| Too broad: "Fix all the tests"             | Specific: "Fix tests/test_validation.py"             |
| No context: "Fix the error"                | Context: Paste error messages and test names         |
| No constraints: Agent refactors everything | Constraints: "Fix tests only" or "Don't change API"  |
| Vague output: "Fix it"                     | Specific: "Return summary of root cause and changes" |

## When NOT to Use

- **Related failures:** Fixing one might fix others—investigate together first
- **Need full context:** Understanding requires seeing entire system
- **Exploratory debugging:** You don't know what's broken yet
- **Shared state:** Agents would edit same files or use same resources

## Verification

After agents return:

1. **Review each summary** - Understand what changed
2. **Check for conflicts** - Did agents edit same code?
3. **Run full suite** - `uv run pytest`
4. **Spot check** - Agents can make systematic errors
