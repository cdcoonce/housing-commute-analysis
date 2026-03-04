"""Python code analyzer using external linters.

This module provides functionality to analyze Python code using external tools
like ruff, with results normalized into the common Issue format.
"""

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from models import (
    AnalysisResult,
    FileType,
    Issue,
    IssueCategory,
    Location,
    Severity,
    SuggestedFix,
)


# Mapping from ruff rule prefixes to our issue categories
RUFF_CATEGORY_MAP: dict[str, IssueCategory] = {
    "E": IssueCategory.PEP8,  # pycodestyle errors
    "W": IssueCategory.PEP8,  # pycodestyle warnings
    "F": IssueCategory.UNUSED_CODE,  # Pyflakes (unused imports, variables)
    "C90": IssueCategory.COMPLEXITY,  # mccabe complexity
    "I": IssueCategory.IMPORT,  # isort
    "N": IssueCategory.PEP8,  # pep8-naming
    "D": IssueCategory.DOCSTRING,  # pydocstyle
    "ANN": IssueCategory.TYPE_HINT,  # flake8-annotations
    "B": IssueCategory.RUNTIME_ERROR,  # flake8-bugbear
    "A": IssueCategory.PEP8,  # flake8-builtins
    "COM": IssueCategory.PEP8,  # flake8-commas
    "DTZ": IssueCategory.RUNTIME_ERROR,  # flake8-datetimez
    "T10": IssueCategory.UNUSED_CODE,  # flake8-debugger
    "EM": IssueCategory.PEP8,  # flake8-errmsg
    "EXE": IssueCategory.RUNTIME_ERROR,  # flake8-executable
    "FA": IssueCategory.IMPORT,  # flake8-future-annotations
    "ISC": IssueCategory.PEP8,  # flake8-implicit-str-concat
    "ICN": IssueCategory.IMPORT,  # flake8-import-conventions
    "G": IssueCategory.PEP8,  # flake8-logging-format
    "INP": IssueCategory.IMPORT,  # flake8-no-pep420
    "PIE": IssueCategory.PEP8,  # flake8-pie
    "T20": IssueCategory.UNUSED_CODE,  # flake8-print
    "PYI": IssueCategory.TYPE_HINT,  # flake8-pyi
    "PT": IssueCategory.PEP8,  # flake8-pytest-style
    "Q": IssueCategory.PEP8,  # flake8-quotes
    "RSE": IssueCategory.RUNTIME_ERROR,  # flake8-raise
    "RET": IssueCategory.PEP8,  # flake8-return
    "SLF": IssueCategory.PEP8,  # flake8-self
    "SLOT": IssueCategory.PEP8,  # flake8-slots
    "SIM": IssueCategory.PEP8,  # flake8-simplify
    "TID": IssueCategory.IMPORT,  # flake8-tidy-imports
    "TCH": IssueCategory.TYPE_HINT,  # flake8-type-checking
    "INT": IssueCategory.PEP8,  # flake8-gettext
    "ARG": IssueCategory.UNUSED_CODE,  # flake8-unused-arguments
    "PTH": IssueCategory.PEP8,  # flake8-use-pathlib
    "TD": IssueCategory.DOCSTRING,  # flake8-todos
    "FIX": IssueCategory.DOCSTRING,  # flake8-fixme
    "ERA": IssueCategory.UNUSED_CODE,  # eradicate
    "PD": IssueCategory.PEP8,  # pandas-vet
    "PGH": IssueCategory.PEP8,  # pygrep-hooks
    "PL": IssueCategory.PEP8,  # Pylint
    "TRY": IssueCategory.RUNTIME_ERROR,  # tryceratops
    "FLY": IssueCategory.PEP8,  # flynt
    "NPY": IssueCategory.PEP8,  # NumPy-specific rules
    "AIR": IssueCategory.PEP8,  # Airflow
    "PERF": IssueCategory.COMPLEXITY,  # Perflint
    "FURB": IssueCategory.PEP8,  # refurb
    "LOG": IssueCategory.PEP8,  # flake8-logging
    "RUF": IssueCategory.PEP8,  # Ruff-specific rules
    "UP": IssueCategory.PEP8,  # pyupgrade
    "S": IssueCategory.RUNTIME_ERROR,  # flake8-bandit (security)
}

# Mapping from ruff rule prefixes to severity levels
RUFF_SEVERITY_MAP: dict[str, Severity] = {
    "E": Severity.WARNING,  # pycodestyle errors are typically style issues
    "W": Severity.INFO,  # pycodestyle warnings
    "F": Severity.WARNING,  # Pyflakes
    "C90": Severity.INFO,  # complexity
    "I": Severity.INFO,  # isort
    "N": Severity.INFO,  # naming
    "D": Severity.INFO,  # docstrings
    "ANN": Severity.INFO,  # annotations
    "B": Severity.WARNING,  # bugbear - potential bugs
    "S": Severity.ERROR,  # security issues
}

# Rules that indicate errors (runtime issues)
ERROR_RULES = {
    "F821",  # undefined name
    "F822",  # undefined name in __all__
    "F823",  # local variable referenced before assignment
    "E999",  # syntax error
    "B018",  # useless expression
    "S101",  # assert used (can be warning in prod)
}


def get_category_for_rule(rule_id: str) -> IssueCategory:
    """Determine the issue category for a ruff rule ID.

    Parameters
    ----------
    rule_id : str
        The ruff rule identifier (e.g., 'F841', 'E501').

    Returns
    -------
    IssueCategory
        The corresponding issue category.
    """
    # Try progressively shorter prefixes (including digits for rules like C90)
    for prefix_len in range(len(rule_id), 0, -1):
        prefix = rule_id[:prefix_len]
        if prefix in RUFF_CATEGORY_MAP:
            return RUFF_CATEGORY_MAP[prefix]
        # Also try without trailing digits for letter-only prefixes
        letter_prefix = "".join(c for c in prefix if not c.isdigit())
        if letter_prefix and letter_prefix in RUFF_CATEGORY_MAP:
            return RUFF_CATEGORY_MAP[letter_prefix]

    # Default to PEP8 for unknown rules
    return IssueCategory.PEP8


def get_severity_for_rule(rule_id: str) -> Severity:
    """Determine the severity level for a ruff rule ID.

    Parameters
    ----------
    rule_id : str
        The ruff rule identifier (e.g., 'F841', 'E501').

    Returns
    -------
    Severity
        The corresponding severity level.
    """
    # Check if it's a known error rule
    if rule_id in ERROR_RULES:
        return Severity.ERROR

    # Try progressively shorter prefixes
    for prefix_len in range(len(rule_id), 0, -1):
        prefix = rule_id[:prefix_len]
        letter_prefix = "".join(c for c in prefix if not c.isdigit())
        if letter_prefix in RUFF_SEVERITY_MAP:
            return RUFF_SEVERITY_MAP[letter_prefix]

    # Default to WARNING for unknown rules
    return Severity.WARNING


def check_ruff_available() -> bool:
    """Check if ruff is available on the system.

    Returns
    -------
    bool
        True if ruff is available, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ruff", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError):
        return False


def run_ruff_check(
    source: str,
    file_path: Optional[Path] = None,
) -> list[dict]:
    """Run ruff check on Python source code.

    Parameters
    ----------
    source : str
        The Python source code to analyze.
    file_path : Optional[Path]
        Path to the source file, used for context. If None, a temporary
        file will be created.

    Returns
    -------
    list[dict]
        List of ruff diagnostic results in JSON format.
    """
    if file_path and file_path.exists():
        # Analyze the actual file
        target = str(file_path)
        temp_file = None
    else:
        # Create a temporary file for the source
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        )
        temp_file.write(source)
        temp_file.close()
        target = temp_file.name

    try:
        # Run ruff with comprehensive rules
        result = subprocess.run(
            [
                "ruff",
                "check",
                "--output-format=json",
                "--select=ALL",  # Enable all rules
                "--ignore=ANN101,ANN102,ANN401",  # Ignore self/cls annotations and Any
                target,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )

        if result.stdout:
            return json.loads(result.stdout)
        return []

    except subprocess.TimeoutExpired:
        return []
    except json.JSONDecodeError:
        return []
    finally:
        if temp_file:
            Path(temp_file.name).unlink(missing_ok=True)


def run_ruff_format_check(
    source: str,
    file_path: Optional[Path] = None,
) -> list[dict]:
    """Run ruff format check to find formatting issues.

    Parameters
    ----------
    source : str
        The Python source code to analyze.
    file_path : Optional[Path]
        Path to the source file.

    Returns
    -------
    list[dict]
        List of formatting issues found.
    """
    if file_path and file_path.exists():
        target = str(file_path)
        temp_file = None
    else:
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
        )
        temp_file.write(source)
        temp_file.close()
        target = temp_file.name

    try:
        # Check if formatting is needed
        result = subprocess.run(
            ["ruff", "format", "--check", "--diff", target],
            capture_output=True,
            text=True,
            timeout=60,
        )

        issues = []
        if result.returncode != 0 and result.stdout:
            # Parse the diff to create formatting issues
            issues.append(
                {
                    "code": "FORMAT",
                    "message": "File needs formatting",
                    "location": {"row": 1, "column": 1},
                    "fix": {"edits": [{"content": result.stdout}]},
                }
            )
        return issues

    except subprocess.TimeoutExpired:
        return []
    finally:
        if temp_file:
            Path(temp_file.name).unlink(missing_ok=True)


def parse_ruff_diagnostic(
    diagnostic: dict,
    file_path: Optional[Path],
    source_lines: list[str],
) -> Issue:
    """Parse a ruff diagnostic into an Issue.

    Parameters
    ----------
    diagnostic : dict
        The ruff diagnostic in JSON format.
    file_path : Optional[Path]
        Path to the source file.
    source_lines : list[str]
        Lines of the source code for context.

    Returns
    -------
    Issue
        The parsed issue.
    """
    rule_id = diagnostic.get("code", "UNKNOWN")
    message = diagnostic.get("message", "Unknown issue")

    # Get location information
    location_data = diagnostic.get("location", {})
    end_location = diagnostic.get("end_location", {})

    line_start = location_data.get("row", 1)
    column_start = location_data.get("column", 1)
    line_end = end_location.get("row")
    column_end = end_location.get("column")

    location = Location(
        file_path=file_path,
        line_start=line_start,
        line_end=line_end if line_end != line_start else None,
        column_start=column_start,
        column_end=column_end,
    )

    # Get context (the relevant source line)
    context = None
    if source_lines and 0 < line_start <= len(source_lines):
        context = source_lines[line_start - 1].rstrip()

    # Check for available fix
    suggested_fix = None
    fix_data = diagnostic.get("fix")
    if fix_data:
        edits = fix_data.get("edits", [])
        if edits:
            # Construct the fix description
            fix_description = fix_data.get("message", f"Apply fix for {rule_id}")
            original = context or ""
            fixed = edits[0].get("content", "")
            suggested_fix = SuggestedFix(
                description=fix_description,
                original_code=original,
                fixed_code=fixed,
                auto_fixable=fix_data.get("applicability", "") == "safe",
            )

    return Issue(
        severity=get_severity_for_rule(rule_id),
        category=get_category_for_rule(rule_id),
        message=message,
        location=location,
        rule_id=rule_id,
        source="ruff",
        suggested_fix=suggested_fix,
        context=context,
    )


def analyze_python(
    source: str,
    file_path: Optional[Path] = None,
) -> AnalysisResult:
    """Analyze Python source code for quality issues.

    Uses ruff as the primary linter to detect PEP8 violations, unused code,
    complexity issues, missing type hints, docstring problems, and more.

    Parameters
    ----------
    source : str
        The Python source code to analyze.
    file_path : Optional[Path]
        Path to the source file, used for reporting locations.

    Returns
    -------
    AnalysisResult
        The analysis results containing all found issues.

    Examples
    --------
    >>> result = analyze_python("x = 1\\nprint(y)")
    >>> result.total_issues > 0
    True
    """
    start_time = time.time()
    issues: list[Issue] = []
    tools_used: list[str] = []
    source_lines = source.splitlines()

    # Run ruff check if available
    if check_ruff_available():
        tools_used.append("ruff")

        # Run main linting checks
        diagnostics = run_ruff_check(source, file_path)
        for diagnostic in diagnostics:
            issue = parse_ruff_diagnostic(diagnostic, file_path, source_lines)
            issues.append(issue)

        # Run format check
        format_issues = run_ruff_format_check(source, file_path)
        for fmt_issue in format_issues:
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    category=IssueCategory.PEP8,
                    message=fmt_issue["message"],
                    location=Location(file_path=file_path, line_start=1),
                    rule_id="FORMAT",
                    source="ruff",
                    suggested_fix=SuggestedFix(
                        description="Format code with ruff",
                        original_code="",
                        fixed_code="",
                        auto_fixable=True,
                    )
                    if fmt_issue.get("fix")
                    else None,
                )
            )

    elapsed = time.time() - start_time

    return AnalysisResult(
        file_type=FileType.PYTHON,
        source_path=file_path,
        issues=issues,
        source_content=source,
        analysis_time_seconds=elapsed,
        tools_used=tools_used,
    )


def analyze_python_file(file_path: Path) -> AnalysisResult:
    """Analyze a Python file for quality issues.

    Parameters
    ----------
    file_path : Path
        Path to the Python file to analyze.

    Returns
    -------
    AnalysisResult
        The analysis results containing all found issues.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    source = file_path.read_text(encoding="utf-8")
    return analyze_python(source, file_path)
