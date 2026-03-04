"""Tests for the report generator module.

This module contains pytest tests for the report generation functionality.
"""

from io import StringIO
from pathlib import Path
import tempfile

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
from report_generator import (
    Colors,
    ConsoleReporter,
    MarkdownReporter,
    colorize,
    generate_console_report,
    generate_markdown_report,
    save_markdown_report,
    severity_color,
    severity_emoji,
    severity_symbol,
)


class TestColorHelpers:
    """Tests for color helper functions."""

    def test_colorize_with_color(self):
        """Test colorize applies color codes."""
        result = colorize("test", Colors.RED, use_color=True)
        assert Colors.RED in result
        assert Colors.RESET in result
        assert "test" in result

    def test_colorize_without_color(self):
        """Test colorize returns plain text when disabled."""
        result = colorize("test", Colors.RED, use_color=False)
        assert result == "test"
        assert Colors.RED not in result

    def test_severity_color_error(self):
        """Test that errors get red color."""
        assert severity_color(Severity.ERROR) == Colors.RED

    def test_severity_color_warning(self):
        """Test that warnings get yellow color."""
        assert severity_color(Severity.WARNING) == Colors.YELLOW

    def test_severity_color_info(self):
        """Test that info gets blue color."""
        assert severity_color(Severity.INFO) == Colors.BLUE

    def test_severity_symbol_error(self):
        """Test error severity symbol."""
        assert severity_symbol(Severity.ERROR) == "✗"

    def test_severity_symbol_warning(self):
        """Test warning severity symbol."""
        assert severity_symbol(Severity.WARNING) == "⚠"

    def test_severity_symbol_info(self):
        """Test info severity symbol."""
        assert severity_symbol(Severity.INFO) == "ℹ"

    def test_severity_emoji_error(self):
        """Test error severity emoji."""
        assert severity_emoji(Severity.ERROR) == "🔴"

    def test_severity_emoji_warning(self):
        """Test warning severity emoji."""
        assert severity_emoji(Severity.WARNING) == "🟡"

    def test_severity_emoji_info(self):
        """Test info severity emoji."""
        assert severity_emoji(Severity.INFO) == "🔵"


class TestConsoleReporter:
    """Tests for console report generation."""

    @pytest.fixture
    def sample_report(self) -> ReviewReport:
        """Create a sample report for testing.

        Returns
        -------
        ReviewReport
            A sample review report.
        """
        issue1 = Issue(
            severity=Severity.ERROR,
            category=IssueCategory.RUNTIME_ERROR,
            message="Undefined variable 'x'",
            location=Location(file_path=Path("test.py"), line_start=10),
            rule_id="F821",
            source="ruff",
            context="print(x)",
        )
        issue2 = Issue(
            severity=Severity.WARNING,
            category=IssueCategory.UNUSED_CODE,
            message="Unused import 'os'",
            location=Location(file_path=Path("test.py"), line_start=1),
            rule_id="F401",
            source="ruff",
            suggested_fix=SuggestedFix(
                description="Remove the unused import",
                original_code="import os",
                fixed_code="",
                auto_fixable=True,
            ),
        )

        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[issue1, issue2],
        )

        return ReviewReport(results=[result], title="Test Report")

    def test_print_report_output(self, sample_report: ReviewReport):
        """Test that print_report produces output."""
        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(sample_report)

        result = output.getvalue()
        assert "Test Report" in result
        assert "test.py" in result
        assert "Undefined variable" in result

    def test_print_report_shows_summary(self, sample_report: ReviewReport):
        """Test that report includes summary statistics."""
        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(sample_report)

        result = output.getvalue()
        assert "Files analyzed:" in result
        assert "Total issues:" in result

    def test_print_report_shows_fix_suggestion(self, sample_report: ReviewReport):
        """Test that fix suggestions are shown."""
        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(sample_report)

        result = output.getvalue()
        assert "Fix:" in result
        assert "Remove the unused import" in result

    def test_print_report_no_issues(self):
        """Test report output when no issues found."""
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("clean.py"),
            issues=[],
        )
        report = ReviewReport(results=[result])

        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(report)

        result_str = output.getvalue()
        assert "No issues found" in result_str

    def test_print_summary(self, sample_report: ReviewReport):
        """Test print_summary produces brief output."""
        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_summary(sample_report)

        result = output.getvalue()
        assert "error" in result.lower()
        assert "warning" in result.lower()

    def test_color_disabled(self, sample_report: ReviewReport):
        """Test that color codes are not present when disabled."""
        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(sample_report)

        result = output.getvalue()
        assert "\033[" not in result


class TestMarkdownReporter:
    """Tests for Markdown report generation."""

    @pytest.fixture
    def sample_report(self) -> ReviewReport:
        """Create a sample report for testing.

        Returns
        -------
        ReviewReport
            A sample review report.
        """
        issue1 = Issue(
            severity=Severity.ERROR,
            category=IssueCategory.RUNTIME_ERROR,
            message="Undefined variable 'x'",
            location=Location(file_path=Path("test.py"), line_start=10),
            rule_id="F821",
            source="ruff",
            context="print(x)",
        )
        issue2 = Issue(
            severity=Severity.WARNING,
            category=IssueCategory.UNUSED_CODE,
            message="Unused import 'os'",
            location=Location(file_path=Path("test.py"), line_start=1),
            rule_id="F401",
            source="ruff",
            suggested_fix=SuggestedFix(
                description="Remove the unused import",
                original_code="import os",
                fixed_code="",
                auto_fixable=True,
            ),
        )

        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[issue1, issue2],
        )

        return ReviewReport(results=[result], title="Test Report")

    def test_generate_report_has_title(self, sample_report: ReviewReport):
        """Test that generated report has title."""
        markdown = generate_markdown_report(sample_report)
        assert "# Test Report" in markdown

    def test_generate_report_has_summary(self, sample_report: ReviewReport):
        """Test that generated report has summary section."""
        markdown = generate_markdown_report(sample_report)
        assert "## Summary" in markdown
        assert "Files analyzed:" in markdown
        assert "Total issues:" in markdown

    def test_generate_report_has_issues_table(self, sample_report: ReviewReport):
        """Test that generated report has issues table."""
        markdown = generate_markdown_report(sample_report)
        assert "| Severity | Line | Rule | Message |" in markdown
        assert "`F821`" in markdown

    def test_generate_report_has_status(self, sample_report: ReviewReport):
        """Test that generated report shows status."""
        markdown = generate_markdown_report(sample_report)
        assert "Status:" in markdown
        # Should be Failed due to error
        assert "Failed" in markdown

    def test_generate_report_includes_context(self, sample_report: ReviewReport):
        """Test that context is included when enabled."""
        markdown = generate_markdown_report(sample_report, include_context=True)
        assert "print(x)" in markdown

    def test_generate_report_excludes_context(self, sample_report: ReviewReport):
        """Test that context can be excluded."""
        markdown = generate_markdown_report(sample_report, include_context=False)
        # Context block should not appear
        assert "**Context:**" not in markdown

    def test_generate_report_includes_fixes(self, sample_report: ReviewReport):
        """Test that fixes are included when enabled."""
        markdown = generate_markdown_report(sample_report, include_fixes=True)
        assert "Suggested Fix:" in markdown
        assert "Remove the unused import" in markdown

    def test_generate_report_clean_file(self):
        """Test report for file with no issues."""
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("clean.py"),
            issues=[],
        )
        report = ReviewReport(results=[result])

        markdown = generate_markdown_report(report)
        assert "No issues found" in markdown
        assert "Passed" in markdown

    def test_generate_report_warnings_only(self):
        """Test status for warnings only."""
        issue = Issue(
            severity=Severity.WARNING,
            category=IssueCategory.PEP8,
            message="Line too long",
            location=Location(file_path=Path("test.py"), line_start=1),
            rule_id="E501",
            source="ruff",
        )
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[issue],
        )
        report = ReviewReport(results=[result])

        markdown = generate_markdown_report(report)
        assert "Passed with warnings" in markdown

    def test_generate_report_has_category_summary(self, sample_report: ReviewReport):
        """Test that category summary is included."""
        markdown = generate_markdown_report(sample_report)
        assert "## Issues by Category" in markdown


class TestSaveMarkdownReport:
    """Tests for saving Markdown reports to files."""

    def test_save_creates_file(self):
        """Test that save_markdown_report creates a file."""
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[],
        )
        report = ReviewReport(results=[result])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            save_markdown_report(report, output_path)

            assert output_path.exists()
            content = output_path.read_text()
            assert "# Code Review Report" in content

    def test_save_with_custom_options(self):
        """Test saving with custom options."""
        issue = Issue(
            severity=Severity.WARNING,
            category=IssueCategory.PEP8,
            message="Test issue",
            location=Location(file_path=Path("test.py"), line_start=1),
            rule_id="TEST",
            source="test",
            context="some code",
        )
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[issue],
        )
        report = ReviewReport(results=[result])

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.md"
            save_markdown_report(
                report,
                output_path,
                include_context=False,
                include_fixes=False,
            )

            content = output_path.read_text()
            assert "**Context:**" not in content


class TestGenerateConsoleReport:
    """Tests for the generate_console_report function."""

    def test_generates_output(self):
        """Test that function generates output."""
        result = AnalysisResult(
            file_type=FileType.PYTHON,
            source_path=Path("test.py"),
            issues=[],
        )
        report = ReviewReport(results=[result])

        output = StringIO()
        generate_console_report(report, use_color=False, output=output)

        assert len(output.getvalue()) > 0


class TestEmptyReport:
    """Tests for empty reports."""

    def test_empty_report_console(self):
        """Test console output for empty report."""
        report = ReviewReport(results=[])

        output = StringIO()
        reporter = ConsoleReporter(use_color=False, output=output)
        reporter.print_report(report)

        result = output.getvalue()
        assert "Files analyzed: 0" in result

    def test_empty_report_markdown(self):
        """Test Markdown output for empty report."""
        report = ReviewReport(results=[])

        markdown = generate_markdown_report(report)
        assert "Files analyzed:** 0" in markdown
        assert "Total issues:** 0" in markdown
