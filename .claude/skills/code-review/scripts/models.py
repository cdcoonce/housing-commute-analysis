"""Data models for the code review system.

This module defines the core data structures used throughout the code review
skill, including severity levels, issue representations, and analysis results.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


class Severity(Enum):
    """Severity levels for code quality issues.

    Attributes
    ----------
    ERROR : str
        Must fix - syntax errors, potential runtime exceptions.
    WARNING : str
        Should fix - unused variables, missing type hints.
    INFO : str
        Consider fixing - complexity suggestions, style improvements.
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueCategory(Enum):
    """Categories of code quality issues.

    Attributes
    ----------
    PEP8 : str
        PEP8 style violations.
    TYPE_HINT : str
        Missing or incorrect type hints.
    DOCSTRING : str
        Missing or malformed docstrings.
    UNUSED_CODE : str
        Unused variables, imports, or functions.
    DUPLICATE_CODE : str
        Duplicated code blocks.
    COMPLEXITY : str
        Cyclomatic complexity issues.
    RUNTIME_ERROR : str
        Potential runtime errors.
    IMPORT : str
        Import-related issues.
    MARKDOWN : str
        Markdown formatting issues.
    MERMAID : str
        Mermaid diagram syntax issues.
    """

    PEP8 = "pep8"
    TYPE_HINT = "type_hint"
    DOCSTRING = "docstring"
    UNUSED_CODE = "unused_code"
    DUPLICATE_CODE = "duplicate_code"
    COMPLEXITY = "complexity"
    RUNTIME_ERROR = "runtime_error"
    IMPORT = "import"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"


class FileType(Enum):
    """Supported file types for analysis.

    Attributes
    ----------
    PYTHON : str
        Python source files (.py).
    MARKDOWN : str
        Markdown documentation files (.md).
    MERMAID : str
        Mermaid diagram files (.mmd, .mermaid) or blocks in markdown.
    """

    PYTHON = "python"
    MARKDOWN = "markdown"
    MERMAID = "mermaid"


@dataclass
class Location:
    """Represents a location in source code.

    Parameters
    ----------
    file_path : Optional[Path]
        Path to the file, None for inline code snippets.
    line_start : int
        Starting line number (1-indexed).
    line_end : Optional[int]
        Ending line number (1-indexed), None for single-line issues.
    column_start : Optional[int]
        Starting column number (1-indexed).
    column_end : Optional[int]
        Ending column number (1-indexed).
    """

    file_path: Optional[Path]
    line_start: int
    line_end: Optional[int] = None
    column_start: Optional[int] = None
    column_end: Optional[int] = None

    def __str__(self) -> str:
        """Return a human-readable location string.

        Returns
        -------
        str
            Formatted location string.
        """
        file_str = str(self.file_path) if self.file_path else "<snippet>"
        location = f"{file_str}:{self.line_start}"
        if self.column_start:
            location += f":{self.column_start}"
        if self.line_end and self.line_end != self.line_start:
            location += f"-{self.line_end}"
        return location


@dataclass
class SuggestedFix:
    """Represents a suggested fix for an issue.

    Parameters
    ----------
    description : str
        Human-readable description of the fix.
    original_code : str
        The original code that should be replaced.
    fixed_code : str
        The corrected code.
    auto_fixable : bool
        Whether this fix can be automatically applied.
    """

    description: str
    original_code: str
    fixed_code: str
    auto_fixable: bool = True


@dataclass
class Issue:
    """Represents a code quality issue.

    Parameters
    ----------
    severity : Severity
        The severity level of the issue.
    category : IssueCategory
        The category of the issue.
    message : str
        Human-readable description of the issue.
    location : Location
        Where the issue was found.
    rule_id : str
        Identifier for the rule that flagged this issue.
    source : str
        The tool or analysis that found this issue (e.g., 'ruff', 'claude').
    suggested_fix : Optional[SuggestedFix]
        A suggested fix for the issue, if available.
    context : Optional[str]
        Additional context or the relevant code snippet.
    """

    severity: Severity
    category: IssueCategory
    message: str
    location: Location
    rule_id: str
    source: str
    suggested_fix: Optional[SuggestedFix] = None
    context: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert the issue to a dictionary representation.

        Returns
        -------
        dict
            Dictionary containing all issue fields.
        """
        result = {
            "severity": self.severity.value,
            "category": self.category.value,
            "message": self.message,
            "location": str(self.location),
            "rule_id": self.rule_id,
            "source": self.source,
        }
        if self.suggested_fix:
            result["suggested_fix"] = {
                "description": self.suggested_fix.description,
                "original_code": self.suggested_fix.original_code,
                "fixed_code": self.suggested_fix.fixed_code,
                "auto_fixable": self.suggested_fix.auto_fixable,
            }
        if self.context:
            result["context"] = self.context
        return result


@dataclass
class AnalysisResult:
    """Results from analyzing a file or code snippet.

    Parameters
    ----------
    file_type : FileType
        The type of file that was analyzed.
    source_path : Optional[Path]
        Path to the analyzed file, None for inline snippets.
    issues : list[Issue]
        List of issues found during analysis.
    source_content : Optional[str]
        The original source content that was analyzed.
    analysis_time_seconds : float
        Time taken to perform the analysis.
    tools_used : list[str]
        List of tools used in the analysis.
    """

    file_type: FileType
    source_path: Optional[Path]
    issues: list[Issue] = field(default_factory=list)
    source_content: Optional[str] = None
    analysis_time_seconds: float = 0.0
    tools_used: list[str] = field(default_factory=list)

    @property
    def error_count(self) -> int:
        """Count of ERROR severity issues.

        Returns
        -------
        int
            Number of error-level issues.
        """
        return sum(1 for issue in self.issues if issue.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        """Count of WARNING severity issues.

        Returns
        -------
        int
            Number of warning-level issues.
        """
        return sum(1 for issue in self.issues if issue.severity == Severity.WARNING)

    @property
    def info_count(self) -> int:
        """Count of INFO severity issues.

        Returns
        -------
        int
            Number of info-level issues.
        """
        return sum(1 for issue in self.issues if issue.severity == Severity.INFO)

    @property
    def total_issues(self) -> int:
        """Total count of all issues.

        Returns
        -------
        int
            Total number of issues.
        """
        return len(self.issues)

    def get_issues_by_category(self, category: IssueCategory) -> list[Issue]:
        """Get all issues of a specific category.

        Parameters
        ----------
        category : IssueCategory
            The category to filter by.

        Returns
        -------
        list[Issue]
            List of issues matching the category.
        """
        return [issue for issue in self.issues if issue.category == category]

    def get_issues_by_severity(self, severity: Severity) -> list[Issue]:
        """Get all issues of a specific severity.

        Parameters
        ----------
        severity : Severity
            The severity to filter by.

        Returns
        -------
        list[Issue]
            List of issues matching the severity.
        """
        return [issue for issue in self.issues if issue.severity == severity]

    def get_fixable_issues(self) -> list[Issue]:
        """Get all issues that have auto-fixable suggestions.

        Returns
        -------
        list[Issue]
            List of issues with auto-fixable suggestions.
        """
        return [
            issue
            for issue in self.issues
            if issue.suggested_fix and issue.suggested_fix.auto_fixable
        ]


@dataclass
class ReviewReport:
    """Complete code review report aggregating all analysis results.

    Parameters
    ----------
    results : list[AnalysisResult]
        List of analysis results for all files/snippets reviewed.
    title : str
        Title for the report.
    """

    results: list[AnalysisResult] = field(default_factory=list)
    title: str = "Code Review Report"

    @property
    def total_files(self) -> int:
        """Total number of files analyzed.

        Returns
        -------
        int
            Number of files/snippets analyzed.
        """
        return len(self.results)

    @property
    def total_issues(self) -> int:
        """Total issues across all files.

        Returns
        -------
        int
            Sum of all issues.
        """
        return sum(result.total_issues for result in self.results)

    @property
    def total_errors(self) -> int:
        """Total error-level issues across all files.

        Returns
        -------
        int
            Sum of all errors.
        """
        return sum(result.error_count for result in self.results)

    @property
    def total_warnings(self) -> int:
        """Total warning-level issues across all files.

        Returns
        -------
        int
            Sum of all warnings.
        """
        return sum(result.warning_count for result in self.results)

    @property
    def total_infos(self) -> int:
        """Total info-level issues across all files.

        Returns
        -------
        int
            Sum of all info items.
        """
        return sum(result.info_count for result in self.results)

    def get_all_issues(self) -> list[Issue]:
        """Get all issues from all results.

        Returns
        -------
        list[Issue]
            Flattened list of all issues.
        """
        all_issues = []
        for result in self.results:
            all_issues.extend(result.issues)
        return all_issues

    def get_all_fixable_issues(self) -> list[Issue]:
        """Get all auto-fixable issues from all results.

        Returns
        -------
        list[Issue]
            List of all auto-fixable issues.
        """
        fixable = []
        for result in self.results:
            fixable.extend(result.get_fixable_issues())
        return fixable
