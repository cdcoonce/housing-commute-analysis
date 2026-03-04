"""Report generator for code review results.

This module generates both Markdown reports and formatted console output
from code review analysis results.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional, TextIO
import sys

from models import (
    AnalysisResult,
    Issue,
    IssueCategory,
    ReviewReport,
    Severity,
)


# ANSI color codes for console output
class Colors:
    """ANSI color codes for terminal output."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"

    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"


def supports_color() -> bool:
    """Check if the terminal supports color output.

    Returns
    -------
    bool
        True if color is supported, False otherwise.
    """
    if not hasattr(sys.stdout, "isatty"):
        return False
    if not sys.stdout.isatty():
        return False
    return True


def colorize(text: str, color: str, use_color: bool = True) -> str:
    """Apply ANSI color to text.

    Parameters
    ----------
    text : str
        The text to colorize.
    color : str
        The ANSI color code.
    use_color : bool
        Whether to apply color.

    Returns
    -------
    str
        The colorized text.
    """
    if use_color:
        return f"{color}{text}{Colors.RESET}"
    return text


def severity_color(severity: Severity) -> str:
    """Get the color for a severity level.

    Parameters
    ----------
    severity : Severity
        The severity level.

    Returns
    -------
    str
        The ANSI color code.
    """
    color_map = {
        Severity.ERROR: Colors.RED,
        Severity.WARNING: Colors.YELLOW,
        Severity.INFO: Colors.BLUE,
    }
    return color_map.get(severity, Colors.RESET)


def severity_symbol(severity: Severity) -> str:
    """Get the symbol for a severity level.

    Parameters
    ----------
    severity : Severity
        The severity level.

    Returns
    -------
    str
        The symbol character.
    """
    symbol_map = {
        Severity.ERROR: "✗",
        Severity.WARNING: "⚠",
        Severity.INFO: "ℹ",
    }
    return symbol_map.get(severity, "•")


def severity_emoji(severity: Severity) -> str:
    """Get the emoji for a severity level (for Markdown).

    Parameters
    ----------
    severity : Severity
        The severity level.

    Returns
    -------
    str
        The emoji string.
    """
    emoji_map = {
        Severity.ERROR: "🔴",
        Severity.WARNING: "🟡",
        Severity.INFO: "🔵",
    }
    return emoji_map.get(severity, "⚪")


class ConsoleReporter:
    """Generate formatted console output for code review results.

    Parameters
    ----------
    use_color : bool
        Whether to use ANSI colors in output.
    output : TextIO
        Output stream to write to.
    """

    def __init__(
        self,
        use_color: Optional[bool] = None,
        output: TextIO = sys.stdout,
    ) -> None:
        """Initialize the console reporter.

        Parameters
        ----------
        use_color : Optional[bool]
            Whether to use colors. Auto-detected if None.
        output : TextIO
            Output stream to write to.
        """
        self.use_color = use_color if use_color is not None else supports_color()
        self.output = output

    def _print(self, text: str = "") -> None:
        """Print text to the output stream.

        Parameters
        ----------
        text : str
            Text to print.
        """
        print(text, file=self.output)

    def _header(self, text: str) -> None:
        """Print a header line.

        Parameters
        ----------
        text : str
            Header text.
        """
        self._print()
        self._print(colorize(f"═══ {text} ═══", Colors.BOLD, self.use_color))

    def _subheader(self, text: str) -> None:
        """Print a subheader line.

        Parameters
        ----------
        text : str
            Subheader text.
        """
        self._print()
        self._print(colorize(f"─── {text} ───", Colors.DIM, self.use_color))

    def print_issue(self, issue: Issue) -> None:
        """Print a single issue.

        Parameters
        ----------
        issue : Issue
            The issue to print.
        """
        color = severity_color(issue.severity)
        symbol = severity_symbol(issue.severity)

        # Location and severity
        loc_str = str(issue.location)
        severity_str = colorize(
            f"{symbol} {issue.severity.value.upper()}",
            color,
            self.use_color,
        )

        self._print(f"  {severity_str} {loc_str}")

        # Message
        self._print(f"    {issue.message}")

        # Rule ID and source
        rule_info = colorize(
            f"    [{issue.rule_id}] ({issue.source})",
            Colors.DIM,
            self.use_color,
        )
        self._print(rule_info)

        # Context
        if issue.context:
            context_line = colorize(f"    │ {issue.context}", Colors.DIM, self.use_color)
            self._print(context_line)

        # Suggested fix
        if issue.suggested_fix:
            fix_label = colorize("    💡 Fix: ", Colors.GREEN, self.use_color)
            self._print(f"{fix_label}{issue.suggested_fix.description}")

        self._print()

    def print_result(self, result: AnalysisResult) -> None:
        """Print analysis results for a single file.

        Parameters
        ----------
        result : AnalysisResult
            The analysis result to print.
        """
        file_name = str(result.source_path) if result.source_path else "<snippet>"
        self._subheader(f"{file_name} ({result.total_issues} issues)")

        if result.total_issues == 0:
            success_msg = colorize("  ✓ No issues found!", Colors.GREEN, self.use_color)
            self._print(success_msg)
            return

        # Group issues by severity
        for severity in [Severity.ERROR, Severity.WARNING, Severity.INFO]:
            issues = result.get_issues_by_severity(severity)
            if issues:
                for issue in issues:
                    self.print_issue(issue)

    def print_report(self, report: ReviewReport) -> None:
        """Print a complete code review report.

        Parameters
        ----------
        report : ReviewReport
            The review report to print.
        """
        self._header(report.title)

        # Summary
        self._print()
        self._print(f"  Files analyzed: {report.total_files}")
        self._print(f"  Total issues: {report.total_issues}")

        # Issue breakdown
        error_str = colorize(f"{report.total_errors} errors", Colors.RED, self.use_color)
        warn_str = colorize(f"{report.total_warnings} warnings", Colors.YELLOW, self.use_color)
        info_str = colorize(f"{report.total_infos} info", Colors.BLUE, self.use_color)
        self._print(f"  Breakdown: {error_str}, {warn_str}, {info_str}")

        # Fixable issues
        fixable_count = len(report.get_all_fixable_issues())
        if fixable_count > 0:
            fix_str = colorize(f"{fixable_count} auto-fixable", Colors.GREEN, self.use_color)
            self._print(f"  {fix_str}")

        # Individual file results
        for result in report.results:
            self.print_result(result)

        # Footer
        self._print()
        if report.total_errors > 0:
            status = colorize("✗ Review failed", Colors.RED, self.use_color)
        elif report.total_warnings > 0:
            status = colorize("⚠ Review passed with warnings", Colors.YELLOW, self.use_color)
        else:
            status = colorize("✓ Review passed", Colors.GREEN, self.use_color)
        self._print(f"  {status}")
        self._print()

    def print_summary(self, report: ReviewReport) -> None:
        """Print a brief summary of the review.

        Parameters
        ----------
        report : ReviewReport
            The review report to summarize.
        """
        total = report.total_issues
        if total == 0:
            self._print(colorize("✓ No issues found", Colors.GREEN, self.use_color))
        else:
            parts = []
            if report.total_errors:
                parts.append(colorize(f"{report.total_errors} errors", Colors.RED, self.use_color))
            if report.total_warnings:
                parts.append(colorize(f"{report.total_warnings} warnings", Colors.YELLOW, self.use_color))
            if report.total_infos:
                parts.append(colorize(f"{report.total_infos} info", Colors.BLUE, self.use_color))
            self._print(f"Found {', '.join(parts)} in {report.total_files} file(s)")


class MarkdownReporter:
    """Generate Markdown reports for code review results.

    Parameters
    ----------
    include_context : bool
        Whether to include code context in the report.
    include_fixes : bool
        Whether to include suggested fixes in the report.
    """

    def __init__(
        self,
        include_context: bool = True,
        include_fixes: bool = True,
    ) -> None:
        """Initialize the Markdown reporter.

        Parameters
        ----------
        include_context : bool
            Whether to include code context.
        include_fixes : bool
            Whether to include suggested fixes.
        """
        self.include_context = include_context
        self.include_fixes = include_fixes

    def generate_report(self, report: ReviewReport) -> str:
        """Generate a complete Markdown report.

        Parameters
        ----------
        report : ReviewReport
            The review report to format.

        Returns
        -------
        str
            The formatted Markdown report.
        """
        lines: list[str] = []

        # Header
        lines.append(f"# {report.title}")
        lines.append("")
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append("")

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Files analyzed:** {report.total_files}")
        lines.append(f"- **Total issues:** {report.total_issues}")
        lines.append(f"  - 🔴 Errors: {report.total_errors}")
        lines.append(f"  - 🟡 Warnings: {report.total_warnings}")
        lines.append(f"  - 🔵 Info: {report.total_infos}")

        fixable = len(report.get_all_fixable_issues())
        if fixable > 0:
            lines.append(f"- **Auto-fixable:** {fixable}")
        lines.append("")

        # Status badge
        if report.total_errors > 0:
            lines.append("**Status:** 🔴 Failed")
        elif report.total_warnings > 0:
            lines.append("**Status:** 🟡 Passed with warnings")
        else:
            lines.append("**Status:** 🟢 Passed")
        lines.append("")

        # Issues by file
        lines.append("## Issues by File")
        lines.append("")

        for result in report.results:
            lines.extend(self._format_result(result))

        # Issues by category summary
        if report.total_issues > 0:
            lines.extend(self._format_category_summary(report))

        return "\n".join(lines)

    def _format_result(self, result: AnalysisResult) -> list[str]:
        """Format analysis results for a single file.

        Parameters
        ----------
        result : AnalysisResult
            The analysis result to format.

        Returns
        -------
        list[str]
            Lines of formatted Markdown.
        """
        lines: list[str] = []
        file_name = str(result.source_path) if result.source_path else "`<snippet>`"

        lines.append(f"### {file_name}")
        lines.append("")

        if result.total_issues == 0:
            lines.append("✅ No issues found")
            lines.append("")
            return lines

        # Stats line
        stats = f"Found {result.total_issues} issue(s): "
        stat_parts = []
        if result.error_count:
            stat_parts.append(f"{result.error_count} error(s)")
        if result.warning_count:
            stat_parts.append(f"{result.warning_count} warning(s)")
        if result.info_count:
            stat_parts.append(f"{result.info_count} info")
        stats += ", ".join(stat_parts)
        lines.append(stats)
        lines.append("")

        # Issues table
        lines.append("| Severity | Line | Rule | Message |")
        lines.append("|----------|------|------|---------|")

        for issue in result.issues:
            emoji = severity_emoji(issue.severity)
            line = issue.location.line_start
            rule = f"`{issue.rule_id}`"
            message = issue.message.replace("|", "\\|")
            lines.append(f"| {emoji} | {line} | {rule} | {message} |")

        lines.append("")

        # Detailed issues with context and fixes
        if self.include_context or self.include_fixes:
            has_details = any(
                issue.context or issue.suggested_fix for issue in result.issues
            )
            if has_details:
                lines.append("<details>")
                lines.append("<summary>Issue Details</summary>")
                lines.append("")

                for issue in result.issues:
                    lines.extend(self._format_issue_detail(issue))

                lines.append("</details>")
                lines.append("")

        return lines

    def _format_issue_detail(self, issue: Issue) -> list[str]:
        """Format detailed information for a single issue.

        Parameters
        ----------
        issue : Issue
            The issue to format.

        Returns
        -------
        list[str]
            Lines of formatted Markdown.
        """
        lines: list[str] = []
        emoji = severity_emoji(issue.severity)

        lines.append(f"#### {emoji} {issue.rule_id}: {issue.message}")
        lines.append("")
        lines.append(f"- **Location:** `{issue.location}`")
        lines.append(f"- **Source:** {issue.source}")
        lines.append(f"- **Category:** {issue.category.value}")
        lines.append("")

        if self.include_context and issue.context:
            lines.append("**Context:**")
            lines.append("```")
            lines.append(issue.context)
            lines.append("```")
            lines.append("")

        if self.include_fixes and issue.suggested_fix:
            fix = issue.suggested_fix
            auto_badge = "✅ Auto-fixable" if fix.auto_fixable else "⚠️ Manual fix"
            lines.append(f"**Suggested Fix:** ({auto_badge})")
            lines.append("")
            lines.append(f"> {fix.description}")
            lines.append("")

            if fix.original_code and fix.fixed_code:
                lines.append("```diff")
                for line in fix.original_code.splitlines():
                    lines.append(f"- {line}")
                for line in fix.fixed_code.splitlines():
                    lines.append(f"+ {line}")
                lines.append("```")
                lines.append("")

        return lines

    def _format_category_summary(self, report: ReviewReport) -> list[str]:
        """Format a summary of issues by category.

        Parameters
        ----------
        report : ReviewReport
            The review report.

        Returns
        -------
        list[str]
            Lines of formatted Markdown.
        """
        lines: list[str] = []
        lines.append("## Issues by Category")
        lines.append("")

        # Count issues by category
        category_counts: dict[IssueCategory, int] = {}
        for issue in report.get_all_issues():
            category_counts[issue.category] = category_counts.get(issue.category, 0) + 1

        if category_counts:
            lines.append("| Category | Count |")
            lines.append("|----------|-------|")
            for category, count in sorted(
                category_counts.items(), key=lambda x: x[1], reverse=True
            ):
                lines.append(f"| {category.value} | {count} |")
            lines.append("")

        return lines


def generate_console_report(
    report: ReviewReport,
    use_color: Optional[bool] = None,
    output: TextIO = sys.stdout,
) -> None:
    """Generate and print a console report.

    Parameters
    ----------
    report : ReviewReport
        The review report to print.
    use_color : Optional[bool]
        Whether to use colors. Auto-detected if None.
    output : TextIO
        Output stream to write to.
    """
    reporter = ConsoleReporter(use_color=use_color, output=output)
    reporter.print_report(report)


def generate_markdown_report(
    report: ReviewReport,
    include_context: bool = True,
    include_fixes: bool = True,
) -> str:
    """Generate a Markdown report string.

    Parameters
    ----------
    report : ReviewReport
        The review report to format.
    include_context : bool
        Whether to include code context.
    include_fixes : bool
        Whether to include suggested fixes.

    Returns
    -------
    str
        The formatted Markdown report.
    """
    reporter = MarkdownReporter(
        include_context=include_context,
        include_fixes=include_fixes,
    )
    return reporter.generate_report(report)


def save_markdown_report(
    report: ReviewReport,
    output_path: Path,
    include_context: bool = True,
    include_fixes: bool = True,
) -> None:
    """Generate and save a Markdown report to a file.

    Parameters
    ----------
    report : ReviewReport
        The review report to save.
    output_path : Path
        Path to save the report to.
    include_context : bool
        Whether to include code context.
    include_fixes : bool
        Whether to include suggested fixes.
    """
    markdown = generate_markdown_report(
        report,
        include_context=include_context,
        include_fixes=include_fixes,
    )
    output_path.write_text(markdown, encoding="utf-8")
