"""Tests for the data models module.

This module contains pytest tests for all data structures in models.py.
"""

from pathlib import Path

import pytest

from models import (
    AnalysisResult,
    FileType,
    Issue,
    IssueCategory,
    Location,
    ReviewReport,
    Severity,
    SuggestedFix,
)


class TestSeverity:
    """Tests for the Severity enum."""

    def test_severity_values(self):
        """Test that severity enum has correct values."""
        assert Severity.ERROR.value == "error"
        assert Severity.WARNING.value == "warning"
        assert Severity.INFO.value == "info"

    def test_severity_members(self):
        """Test that all expected severity levels exist."""
        members = list(Severity)
        assert len(members) == 3
        assert Severity.ERROR in members
        assert Severity.WARNING in members
        assert Severity.INFO in members


class TestIssueCategory:
    """Tests for the IssueCategory enum."""

    def test_python_categories_exist(self):
        """Test that Python-related categories exist."""
        assert IssueCategory.PEP8.value == "pep8"
        assert IssueCategory.TYPE_HINT.value == "type_hint"
        assert IssueCategory.DOCSTRING.value == "docstring"
        assert IssueCategory.UNUSED_CODE.value == "unused_code"
        assert IssueCategory.DUPLICATE_CODE.value == "duplicate_code"
        assert IssueCategory.COMPLEXITY.value == "complexity"
        assert IssueCategory.RUNTIME_ERROR.value == "runtime_error"
        assert IssueCategory.IMPORT.value == "import"

    def test_documentation_categories_exist(self):
        """Test that documentation-related categories exist."""
        assert IssueCategory.MARKDOWN.value == "markdown"
        assert IssueCategory.MERMAID.value == "mermaid"


class TestFileType:
    """Tests for the FileType enum."""

    def test_file_type_values(self):
        """Test that file type enum has correct values."""
        assert FileType.PYTHON.value == "python"
        assert FileType.MARKDOWN.value == "markdown"
        assert FileType.MERMAID.value == "mermaid"


class TestLocation:
    """Tests for the Location dataclass."""

    def test_location_with_file_path(self):
        """Test location with a file path."""
        loc = Location(
            file_path=Path("test.py"),
            line_start=10,
        )
        assert loc.file_path == Path("test.py")
        assert loc.line_start == 10
        assert loc.line_end is None

    def test_location_str_simple(self):
        """Test string representation for simple location."""
        loc = Location(file_path=Path("test.py"), line_start=10)
        assert str(loc) == "test.py:10"

    def test_location_str_with_column(self):
        """Test string representation with column."""
        loc = Location(
            file_path=Path("test.py"),
            line_start=10,
            column_start=5,
        )
        assert str(loc) == "test.py:10:5"

    def test_location_str_with_range(self):
        """Test string representation with line range."""
        loc = Location(
            file_path=Path("test.py"),
            line_start=10,
            line_end=15,
        )
        assert str(loc) == "test.py:10-15"

    def test_location_str_snippet(self):
        """Test string representation for inline snippet."""
        loc = Location(file_path=None, line_start=1)
        assert str(loc) == "<snippet>:1"

    def test_location_same_line_no_range(self):
        """Test that same start and end line doesn't show range."""
        loc = Location(
            file_path=Path("test.py"),
            line_start=10,
            line_end=10,
        )
        assert str(loc) == "test.py:10"


class TestSuggestedFix:
    """Tests for the SuggestedFix dataclass."""

    def test_suggested_fix_creation(self):
        """Test creating a suggested fix."""
        fix = SuggestedFix(
            description="Remove unused variable",
            original_code="x = 1",
            fixed_code="",
            auto_fixable=True,
        )
        assert fix.description == "Remove unused variable"
        assert fix.original_code == "x = 1"
        assert fix.fixed_code == ""
        assert fix.auto_fixable is True

    def test_suggested_fix_default_auto_fixable(self):
        """Test that auto_fixable defaults to True."""
        fix = SuggestedFix(
            description="Test fix",
            original_code="old",
            fixed_code="new",
        )
        assert fix.auto_fixable is True


class TestIssue:
    """Tests for the Issue dataclass."""

    @pytest.fixture
    def sample_issue(self) -> Issue:
        """Create a sample issue for testing.

        Returns
        -------
        Issue
            A sample issue instance.
        """
        return Issue(
            severity=Severity.WARNING,
            category=IssueCategory.UNUSED_CODE,
            message="Unused variable 'x'",
            location=Location(file_path=Path("test.py"), line_start=10),
            rule_id="F841",
            source="ruff",
            suggested_fix=SuggestedFix(
                description="Remove the unused variable",
                original_code="x = 1",
                fixed_code="",
            ),
            context="x = 1  # noqa",
        )

    def test_issue_creation(self, sample_issue: Issue):
        """Test creating an issue with all fields."""
        assert sample_issue.severity == Severity.WARNING
        assert sample_issue.category == IssueCategory.UNUSED_CODE
        assert sample_issue.message == "Unused variable 'x'"
        assert sample_issue.rule_id == "F841"
        assert sample_issue.source == "ruff"
        assert sample_issue.suggested_fix is not None
        assert sample_issue.context == "x = 1  # noqa"

    def test_issue_to_dict(self, sample_issue: Issue):
        """Test converting issue to dictionary."""
        result = sample_issue.to_dict()
        assert result["severity"] == "warning"
        assert result["category"] == "unused_code"
        assert result["message"] == "Unused variable 'x'"
        assert result["rule_id"] == "F841"
        assert result["source"] == "ruff"
        assert "suggested_fix" in result
        assert result["suggested_fix"]["description"] == "Remove the unused variable"

    def test_issue_to_dict_without_fix(self):
        """Test converting issue without fix to dictionary."""
        issue = Issue(
            severity=Severity.ERROR,
            category=IssueCategory.RUNTIME_ERROR,
            message="Division by zero",
            location=Location(file_path=Path("test.py"), line_start=5),
            rule_id="E001",
            source="claude",
        )
        result = issue.to_dict()
        assert "suggested_fix" not in result


class TestAnalysisResult:
    """Tests for the AnalysisResult dataclass."""

    @pytest.fixture
    def sample_result(self) -> AnalysisResult:
        """Create a sample analysis result for testing.

        Returns
        -------
        AnalysisResult
            A sample analysis result instance.
        """
        issues = [
            Issue(
                severity=Severity.ERROR,
                category=IssueCategory.RUNTIME_ERROR,
                message="Error 1",
                location=Location(file_path=Path("test.py"), line_start=1),
                rule_id="E001",
                source="ruff",
            ),
            Issue(
                severity=Severity.WARNING,
                category=IssueCategory.UNUSED_CODE,
                message="Warning 1",
                location=Location(file_path=Path("test.py"), line_start=2),
                rule_id="W001",
                source="ruff",
                suggested_fix=SuggestedFix(
                    description="Fix it",
                    original_code="old",
                    fixed_code="new",
                ),
            ),
            Issue(
                severity=Severity.WARNING,
                category=IssueCategory.PEP8,
                message="Warning 2",
                location=Location(file_path=Path("test.py"), line_start=3),
                rule_id="W002",
                source="ruff",
            ),
            Issue(
                severity=Severity.INFO,
                category=IssueCategory.COMPLEXITY,
                message="Info 1",
                location=Location(file_path=Path("test.py"), line_start=4),
                rule_id="I001",
                source="claude",
            ),
        ]
        return AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=issues,
            analysis_time_seconds=1.5,
            tools_used=["ruff", "claude"],
        )

    def test_analysis_result_counts(self, sample_result: AnalysisResult):
        """Test issue count properties."""
        assert sample_result.error_count == 1
        assert sample_result.warning_count == 2
        assert sample_result.info_count == 1
        assert sample_result.total_issues == 4

    def test_get_issues_by_category(self, sample_result: AnalysisResult):
        """Test filtering issues by category."""
        unused = sample_result.get_issues_by_category(IssueCategory.UNUSED_CODE)
        assert len(unused) == 1
        assert unused[0].message == "Warning 1"

    def test_get_issues_by_severity(self, sample_result: AnalysisResult):
        """Test filtering issues by severity."""
        warnings = sample_result.get_issues_by_severity(Severity.WARNING)
        assert len(warnings) == 2

    def test_get_fixable_issues(self, sample_result: AnalysisResult):
        """Test getting auto-fixable issues."""
        fixable = sample_result.get_fixable_issues()
        assert len(fixable) == 1
        assert fixable[0].message == "Warning 1"

    def test_empty_result(self):
        """Test analysis result with no issues."""
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("clean.py"),
        )
        assert result.total_issues == 0
        assert result.error_count == 0


class TestReviewReport:
    """Tests for the ReviewReport dataclass."""

    @pytest.fixture
    def sample_report(self) -> ReviewReport:
        """Create a sample review report for testing.

        Returns
        -------
        ReviewReport
            A sample review report instance.
        """
        result1 = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("file1.py"),
            issues=[
                Issue(
                    severity=Severity.ERROR,
                    category=IssueCategory.RUNTIME_ERROR,
                    message="Error in file1",
                    location=Location(file_path=Path("file1.py"), line_start=1),
                    rule_id="E001",
                    source="ruff",
                ),
            ],
        )
        result2 = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("file2.py"),
            issues=[
                Issue(
                    severity=Severity.WARNING,
                    category=IssueCategory.PEP8,
                    message="Warning in file2",
                    location=Location(file_path=Path("file2.py"), line_start=1),
                    rule_id="W001",
                    source="ruff",
                    suggested_fix=SuggestedFix(
                        description="Fix",
                        original_code="old",
                        fixed_code="new",
                    ),
                ),
            ],
        )
        return ReviewReport(
            results=[result1, result2],
            title="Test Report",
        )

    def test_report_totals(self, sample_report: ReviewReport):
        """Test report total calculations."""
        assert sample_report.total_files == 2
        assert sample_report.total_issues == 2
        assert sample_report.total_errors == 1
        assert sample_report.total_warnings == 1
        assert sample_report.total_infos == 0

    def test_get_all_issues(self, sample_report: ReviewReport):
        """Test getting all issues from report."""
        all_issues = sample_report.get_all_issues()
        assert len(all_issues) == 2

    def test_get_all_fixable_issues(self, sample_report: ReviewReport):
        """Test getting all fixable issues from report."""
        fixable = sample_report.get_all_fixable_issues()
        assert len(fixable) == 1
        assert fixable[0].message == "Warning in file2"

    def test_empty_report(self):
        """Test empty review report."""
        report = ReviewReport()
        assert report.total_files == 0
        assert report.total_issues == 0
        assert report.title == "Code Review Report"
