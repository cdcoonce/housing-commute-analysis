# Root Cause Tracing

Bugs often manifest deep in the call stack (file created in wrong location, database opened with wrong path). Your instinct is to fix where the error appears, but that's treating a symptom.

**Core principle:** Trace backward through the call chain until you find the original trigger, then fix at the source.

## When to Use

- Error happens deep in execution (not at entry point)
- Stack trace shows long call chain
- Unclear where invalid data originated
- Need to find which test/code triggers the problem

## The Tracing Process

### 1. Observe the Symptom
```
Error: FileNotFoundError in /path/to/output/data.parquet
```

### 2. Find Immediate Cause
**What code directly causes this?**
```python
df.write_parquet(output_path)  # output_path is wrong
```

### 3. Ask: What Called This?
```python
DataExporter.export(output_path)
  → called by Pipeline.run()
  → called by DagsterAsset.materialize()
  → called by test in tests/test_pipeline.py::test_export()
```

### 4. Keep Tracing Up
**What value was passed?**
- `output_path = ''` (empty string!)
- Empty string resolves to current directory
- That's the source code directory!

### 5. Find Original Trigger
**Where did empty string come from?**
```python
config = load_config()  # Returns {'output_dir': ''}
Pipeline(output_dir=config['output_dir'])  # Bug: missing config!
```

## Adding Stack Traces in Python

When you can't trace manually, add instrumentation:

```python
import sys
import traceback

def write_output(output_path: str, df):
    # Capture full stack trace
    stack = ''.join(traceback.format_stack())

    # Log to stderr (always visible in pytest)
    print(f"DEBUG write_output:", file=sys.stderr)
    print(f"  output_path: {output_path!r}", file=sys.stderr)
    print(f"Stack trace:\n{stack}", file=sys.stderr)

    df.write_parquet(output_path)
```

**Run and capture:**
```bash
# Show all output during test run
uv run pytest -s tests/test_pipeline.py 2>&1 | grep 'DEBUG write_output'

# Or with verbose output
uv run pytest -vvs tests/test_pipeline.py
```

## Finding Which Test Causes Pollution

If something appears during tests but you don't know which test:

### Option 1: Bisect with pytest
```bash
uv run pytest --collect-only -q | head -20  # See test list
uv run pytest tests/test_a.py  # Run subset, check for artifact
uv run pytest tests/test_b.py  # Narrow down
```

### Option 2: Custom bisection
```python
#!/usr/bin/env python3
# find_polluter.py
import subprocess
from pathlib import Path
import glob

def find_polluter(artifact: str, test_pattern: str):
    """Find which test creates the artifact."""
    for test_file in glob.glob(test_pattern, recursive=True):
        # Clean artifact first
        Path(artifact).unlink(missing_ok=True)

        print(f"Testing: {test_file}")
        subprocess.run(['uv', 'run', 'pytest', '-xvs', test_file])

        if Path(artifact).exists():
            print(f"FOUND POLLUTER: {test_file}")
            return test_file

    print("No polluter found")
    return None

if __name__ == "__main__":
    find_polluter('unwanted_file.txt', 'tests/**/*.py')
```

## pytest Fixtures for Better Tracing

Use fixtures with proper setup/teardown to prevent pollution:

```python
import pytest
import tempfile
import shutil
from pathlib import Path

@pytest.fixture
def temp_workspace():
    """Create a temporary workspace that self-cleans."""
    temp_dir = tempfile.mkdtemp(prefix="test_")
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)

@pytest.fixture
def safe_output_dir(temp_workspace):
    """Output directory that prevents writing to source."""
    output_dir = temp_workspace / "output"
    output_dir.mkdir()
    return output_dir
```

## Real Example: Empty output_dir

**Symptom:** Data written to `src/` instead of `output/`

**Trace chain:**
1. `df.write_parquet('')` ← empty path
2. Pipeline called with empty output_dir
3. Config loaded before environment setup
4. Test accessed config at module level

**Root cause:** Module-level variable initialization

**Fix:** Made output_dir a required parameter that validates non-empty:

```python
# BAD - module level access
class TestPipeline:
    config = load_config()  # Returns {'output_dir': ''}
    pipeline = Pipeline(config['output_dir'])  # BUG!

# GOOD - access within test
class TestPipeline:
    def test_export(self, temp_workspace):
        config = load_config(output_dir=temp_workspace)
        pipeline = Pipeline(config['output_dir'])  # Safe!
```

**Defense in depth:**
```python
# Layer 1: Validate on init
def __init__(self, output_dir: str):
    if not output_dir:
        raise ValueError("output_dir cannot be empty")

# Layer 2: Validate before write
def write_output(self, path: str):
    if not path or path == ".":
        raise ValueError(f"Invalid output path: {path!r}")
```

## pytest Debugging Tools

```bash
# Drop into pdb on failures
uv run pytest --pdb

# Show local variables on failure
uv run pytest -l

# Maximum verbosity
uv run pytest -vvv

# Show print statements
uv run pytest -s
```

## Key Principle

**NEVER fix just where the error appears.** Trace back to find the original trigger.

## Quick Reference Checklist

When debugging test pollution or deep stack issues:

1. ☐ Add `print(..., file=sys.stderr)` at problem location
2. ☐ Include full stack trace: `traceback.format_stack()`
3. ☐ Log all parameters
4. ☐ Run with `uv run pytest -vvs`
5. ☐ Trace backward through each function call
6. ☐ Find where bad value originates
7. ☐ Fix at source, not symptom
8. ☐ Add validation at each layer
9. ☐ Use fixtures to control initialization
10. ☐ Verify fix prevents recurrence
