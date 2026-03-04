"""Tests for the Markdown analyzer module.

This module contains pytest tests for the Markdown documentation analyzer.
"""

from pathlib import Path
import tempfile

import pytest

from models import FileType, IssueCategory, Severity
from markdown_analyzer import (
    MarkdownAnalyzer,
    analyze_markdown,
    analyze_markdown_file,
)


class TestMarkdownAnalyzerHeadings:
    """Tests for heading structure analysis."""

    def test_document_starts_with_h1(self):
        """Test that documents should start with h1."""
        content = "## Not an h1\n\nSome content"
        result = analyze_markdown(content)

        md041_issues = [i for i in result.issues if i.rule_id == "MD041"]
        assert len(md041_issues) == 1
        assert md041_issues[0].severity == Severity.WARNING

    def test_document_with_proper_h1(self):
        """Test that proper h1 doesn't trigger warning."""
        content = "# Proper Title\n\nSome content"
        result = analyze_markdown(content)

        md041_issues = [i for i in result.issues if i.rule_id == "MD041"]
        assert len(md041_issues) == 0

    def test_multiple_h1_headings(self):
        """Test detection of multiple h1 headings."""
        content = "# First Title\n\n# Second Title\n\nContent"
        result = analyze_markdown(content)

        md025_issues = [i for i in result.issues if i.rule_id == "MD025"]
        assert len(md025_issues) == 1

    def test_skipped_heading_levels(self):
        """Test detection of skipped heading levels."""
        content = "# Title\n\n### Skipped h2\n\nContent"
        result = analyze_markdown(content)

        md001_issues = [i for i in result.issues if i.rule_id == "MD001"]
        assert len(md001_issues) == 1
        assert "skipped" in md001_issues[0].message.lower()

    def test_proper_heading_sequence(self):
        """Test that proper heading sequence passes."""
        content = "# Title\n\n## Section\n\n### Subsection\n\nContent"
        result = analyze_markdown(content)

        md001_issues = [i for i in result.issues if i.rule_id == "MD001"]
        assert len(md001_issues) == 0

    def test_duplicate_headings(self):
        """Test detection of duplicate headings."""
        content = "# Title\n\n## Section\n\n## Section\n\nContent"
        result = analyze_markdown(content)

        md024_issues = [i for i in result.issues if i.rule_id == "MD024"]
        assert len(md024_issues) == 1
        assert md024_issues[0].severity == Severity.INFO


class TestMarkdownAnalyzerLinks:
    """Tests for link analysis."""

    def test_empty_link_text(self):
        """Test detection of empty link text."""
        content = "# Title\n\n[](https://example.com)"
        result = analyze_markdown(content)

        md045_issues = [i for i in result.issues if i.rule_id == "MD045"]
        assert len(md045_issues) >= 1

    def test_empty_link_url(self):
        """Test detection of empty link URL."""
        content = "# Title\n\n[Click here]()"
        result = analyze_markdown(content)

        md042_issues = [i for i in result.issues if i.rule_id == "MD042"]
        assert len(md042_issues) == 1
        assert md042_issues[0].severity == Severity.ERROR

    def test_valid_link(self):
        """Test that valid links pass."""
        content = "# Title\n\n[Example](https://example.com)"
        result = analyze_markdown(content)

        link_issues = [
            i for i in result.issues if i.rule_id in ("MD042", "MD045", "MD052")
        ]
        assert len(link_issues) == 0

    def test_broken_relative_link(self):
        """Test detection of broken relative links."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            md_file = tmppath / "test.md"
            md_file.write_text("# Title\n\n[Link](nonexistent.md)")

            result = analyze_markdown_file(md_file)

            md052_issues = [i for i in result.issues if i.rule_id == "MD052"]
            assert len(md052_issues) == 1
            assert "not found" in md052_issues[0].message.lower()


class TestMarkdownAnalyzerImages:
    """Tests for image analysis."""

    def test_missing_alt_text(self):
        """Test detection of missing alt text."""
        content = "# Title\n\n![](image.png)"
        result = analyze_markdown(content)

        md045_issues = [
            i for i in result.issues
            if i.rule_id == "MD045" and "alt text" in i.message.lower()
        ]
        assert len(md045_issues) == 1
        assert md045_issues[0].severity == Severity.WARNING

    def test_image_with_alt_text(self):
        """Test that images with alt text pass."""
        content = "# Title\n\n![Alt description](image.png)"
        result = analyze_markdown(content)

        alt_issues = [
            i for i in result.issues
            if i.rule_id == "MD045" and "alt text" in i.message.lower()
        ]
        assert len(alt_issues) == 0


class TestMarkdownAnalyzerReferenceLinks:
    """Tests for reference link analysis."""

    def test_undefined_reference_link(self):
        """Test detection of undefined reference links."""
        content = "# Title\n\n[Link][undefined]"
        result = analyze_markdown(content)

        md052_issues = [
            i for i in result.issues
            if i.rule_id == "MD052" and "undefined reference" in i.message.lower()
        ]
        assert len(md052_issues) == 1

    def test_defined_reference_link(self):
        """Test that defined reference links pass."""
        content = "# Title\n\n[Link][ref]\n\n[ref]: https://example.com"
        result = analyze_markdown(content)

        ref_issues = [
            i for i in result.issues
            if i.rule_id == "MD052" and "undefined reference" in i.message.lower()
        ]
        assert len(ref_issues) == 0


class TestMarkdownAnalyzerFormatting:
    """Tests for formatting analysis."""

    def test_trailing_whitespace(self):
        """Test detection of trailing whitespace."""
        content = "# Title\n\nSome text with trailing   \n\nMore text"
        result = analyze_markdown(content)

        md009_issues = [i for i in result.issues if i.rule_id == "MD009"]
        assert len(md009_issues) >= 1
        assert md009_issues[0].severity == Severity.INFO

    def test_multiple_blank_lines(self):
        """Test detection of multiple consecutive blank lines."""
        content = "# Title\n\n\n\nContent with too many blank lines"
        result = analyze_markdown(content)

        md012_issues = [i for i in result.issues if i.rule_id == "MD012"]
        assert len(md012_issues) >= 1

    def test_missing_blank_after_heading(self):
        """Test detection of missing blank line after heading."""
        content = "# Title\nNo blank line after heading"
        result = analyze_markdown(content)

        md022_issues = [i for i in result.issues if i.rule_id == "MD022"]
        assert len(md022_issues) >= 1


class TestMarkdownAnalyzerCodeBlocks:
    """Tests for code block analysis."""

    def test_code_block_without_language(self):
        """Test detection of code blocks without language identifier."""
        content = "# Title\n\n```\nsome code\n```"
        result = analyze_markdown(content)

        md040_issues = [i for i in result.issues if i.rule_id == "MD040"]
        assert len(md040_issues) == 1

    def test_code_block_with_language(self):
        """Test that code blocks with language pass."""
        content = "# Title\n\n```python\nprint('hello')\n```"
        result = analyze_markdown(content)

        md040_issues = [i for i in result.issues if i.rule_id == "MD040"]
        assert len(md040_issues) == 0


class TestMarkdownAnalyzeFunction:
    """Tests for the main analyze_markdown function."""

    def test_returns_analysis_result(self):
        """Test that function returns AnalysisResult."""
        result = analyze_markdown("# Title\n\nContent")
        assert result.file_type == FileType.MARKDOWN

    def test_includes_source_content(self):
        """Test that result includes source content."""
        content = "# Title\n\nContent"
        result = analyze_markdown(content)
        assert result.source_content == content

    def test_includes_tools_used(self):
        """Test that result includes tools used."""
        result = analyze_markdown("# Title\n\nContent")
        assert "markdown-analyzer" in result.tools_used

    def test_records_analysis_time(self):
        """Test that analysis time is recorded."""
        result = analyze_markdown("# Title\n\nContent")
        assert result.analysis_time_seconds >= 0

    def test_with_file_path(self):
        """Test analysis with file path specified."""
        result = analyze_markdown("# Title", file_path=Path("test.md"))
        assert result.source_path == Path("test.md")


class TestMarkdownAnalyzeFile:
    """Tests for the analyze_markdown_file function."""

    def test_analyze_existing_file(self):
        """Test analyzing an existing Markdown file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as tmp:
            tmp.write("## No h1\n\nContent")
            tmp.flush()
            tmp_path = Path(tmp.name)

        try:
            result = analyze_markdown_file(tmp_path)
            assert result.source_path == tmp_path
            assert result.total_issues > 0
        finally:
            tmp_path.unlink()

    def test_analyze_nonexistent_file(self):
        """Test that analyzing a nonexistent file raises an error."""
        with pytest.raises(FileNotFoundError):
            analyze_markdown_file(Path("/nonexistent/file.md"))


class TestMarkdownAnalyzerSuggestedFixes:
    """Tests for suggested fixes."""

    def test_fix_for_heading_level(self):
        """Test that heading level issues have suggested fixes."""
        content = "### Skipped to h3\n\nContent"
        result = analyze_markdown(content)

        md041_issues = [i for i in result.issues if i.rule_id == "MD041"]
        assert len(md041_issues) > 0
        assert md041_issues[0].suggested_fix is not None
        assert md041_issues[0].suggested_fix.auto_fixable

    def test_fix_for_multiple_blank_lines(self):
        """Test that multiple blank lines have suggested fix."""
        content = "# Title\n\n\n\nContent"
        result = analyze_markdown(content)

        md012_issues = [i for i in result.issues if i.rule_id == "MD012"]
        assert len(md012_issues) > 0
        assert md012_issues[0].suggested_fix is not None
        assert md012_issues[0].suggested_fix.fixed_code == "\n\n"


class TestCleanMarkdown:
    """Tests with clean Markdown content."""

    def test_clean_document(self):
        """Test that a well-formed document has minimal issues."""
        content = """# My Document

This is a well-formed Markdown document.

## Section One

Some content here with a [valid link](https://example.com).

## Section Two

More content with properly formatted code:

```python
print("Hello, World!")
```

### Subsection

Final content.
"""
        result = analyze_markdown(content)
        # Well-formed content should have few or no errors
        assert result.error_count == 0
