---
name: code-review
description: AI-powered code quality analysis for Python, Markdown, and Mermaid diagrams. Use this skill when: (1) reviewing code for quality issues, (2) checking Python files for PEP8 violations, unused code, missing type hints, docstring problems, complexity issues, or potential runtime errors, (3) validating Markdown documentation for broken links, heading structure, or formatting issues, (4) validating Mermaid diagram syntax, (5) the user asks for a "code review" or "quality check", (6) analyzing code snippets pasted in conversation, or (7) suggesting and applying fixes for code quality issues.
---

# Code Review Skill

Analyze Python code, Markdown documentation, and Mermaid diagrams for quality issues. Combines external linters (ruff) with Claude's analysis to provide comprehensive code review with suggested fixes.
Should not just be about running ruff and other linters, instead checks code for conformance with good software engineering practice (SOLID, DRY, YAGNI, simplicity not complexity); security vulnerabilities; and descriptive variable naming e.g.
Don't do this:

```python
pkb = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

```

Instead do this:

```python
private_key_bytes = p_key.private_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )

```

## Quick Start

### Analyze Python Code

```python
from python_analyzer import analyze_python, analyze_python_file
from report_generator import generate_console_report, generate_markdown_report
from models import ReviewReport

# Analyze a code snippet
result = analyze_python(code_string)

# Analyze a file
result = analyze_python_file(Path("src/module.py"))

# Generate report
report = ReviewReport(results=[result], title="Code Review")
generate_console_report(report)  # Console output
markdown = generate_markdown_report(report)  # Markdown string
```

### Analyze Markdown

```python
from markdown_analyzer import analyze_markdown, analyze_markdown_file

result = analyze_markdown(content)
# or
result = analyze_markdown_file(Path("README.md"))
```

### Analyze Mermaid Diagrams

For Mermaid validation, use Claude's understanding combined with web search for latest syntax. See [mermaid-checks.md](references/mermaid-checks.md).

## Workflow

1. **Receive code** - From file path or pasted snippet
2. **Detect file type** - Python (.py), Markdown (.md), or Mermaid (.mmd, code blocks)
3. **Run analysis** - External linters first, then Claude's analysis
4. **Generate report** - Both console and markdown formats
5. **Save report** - Write markdown report to `docs/code_reviews/{YYYY-MM-DD}_{file_name}.md` (create directory if needed)
6. **Review fixes** - Present suggested fixes to user
7. **Apply fixes** - With user approval (flexible approval modes)
8. **Check README** - Before pushing, verify README.md reflects current changes (new features, modified APIs, updated dependencies, changed configuration)

## Analysis Capabilities

### Python (via ruff + Claude)

| Category       | Examples                                  | Severity     |
| -------------- | ----------------------------------------- | ------------ |
| PEP8           | Line length, indentation, whitespace      | WARNING/INFO |
| Unused Code    | Unused imports, variables, arguments      | WARNING      |
| Type Hints     | Missing annotations on functions          | INFO         |
| Docstrings     | Missing/malformed numpy-style docstrings  | INFO         |
| Complexity     | Functions with high cyclomatic complexity | INFO         |
| Runtime Errors | Undefined names, syntax errors            | ERROR        |
| Imports        | Unsorted imports, banned imports          | INFO         |

### Markdown

| Check               | Description                            | Severity |
| ------------------- | -------------------------------------- | -------- |
| Heading Structure   | Proper h1→h2→h3 sequence               | WARNING  |
| Broken Links        | File links that don't exist            | ERROR    |
| Missing Alt Text    | Images without accessibility text      | WARNING  |
| Formatting          | Trailing whitespace, blank lines       | INFO     |
| Code Blocks         | Missing language identifier            | INFO     |
| Encoding Corruption | UTF-8 chars appearing as Ã—, âœ", etc. | ERROR    |

### Mermaid

Search web for latest Mermaid.js documentation before validating. Check:

- Diagram type declaration
- Node/edge syntax
- Structural correctness
- Relationship definitions

## Output Formats

### Console (Interactive)

Colorized output with severity indicators:

- ✗ ERROR (red) - Must fix
- ⚠ WARNING (yellow) - Should fix
- ℹ INFO (blue) - Consider fixing

### Markdown Report

Saved to `docs/code_reviews/{YYYY-MM-DD}_{file_name}.md`. For multi-file reviews, use a descriptive name (e.g., `2026-03-02_full_repo_review.md`).

Structured report with:

- Summary statistics
- Status badge (Passed/Failed)
- Issues table per file
- Expandable issue details
- Category breakdown

## Fix Application

Fixes can be approved:

- **All at once** - Apply all auto-fixable issues
- **By category** - Apply all PEP8 fixes, skip docstrings
- **By severity** - Fix errors first, then warnings
- **By file** - Fix specific files only
- **Individually** - Review each fix

See [fix-workflow.md](references/fix-workflow.md) for detailed workflow.

## Reference Documentation

- [python-checks.md](references/python-checks.md) - Python rule details
- [markdown-checks.md](references/markdown-checks.md) - Markdown rule details
- [mermaid-checks.md](references/mermaid-checks.md) - Mermaid validation guide
- [fix-workflow.md](references/fix-workflow.md) - Fix approval workflow

## Example Usage Patterns

### Full Repository Review

```
User: "Review the code quality in my project"

1. List Python and Markdown files
2. Analyze each file
3. Aggregate into ReviewReport
4. Present console summary
5. Save report to docs/code_reviews/{YYYY-MM-DD}_full_repo_review.md
6. Offer to apply fixes
```

### Quick Code Check

```
User: [pastes code snippet]
      "Any issues with this?"

1. Analyze snippet directly
2. Report issues inline
3. Suggest specific fixes
```

### Pre-Commit Review

```
User: "Check these files before I commit"

1. Analyze specified files
2. Focus on errors and warnings
3. Block if errors found
4. Apply quick fixes if approved
5. Check if README needs updating based on changes
6. Update README if new features, APIs, or dependencies changed
```

## Scripts

| Script                 | Purpose                                           |
| ---------------------- | ------------------------------------------------- |
| `models.py`            | Data structures (Issue, Severity, AnalysisResult) |
| `python_analyzer.py`   | Python analysis with ruff                         |
| `markdown_analyzer.py` | Markdown quality checks                           |
| `report_generator.py`  | Console and Markdown report generation            |

## Requirements

- Python 3.10+
- ruff (installed via pip)
- Web access for Mermaid documentation lookup
