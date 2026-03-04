"""Tests for src.models.reporting module."""

from datetime import date

import pytest

from src.models.reporting import (
    append_section,
    create_analysis_summary_header,
    save_markdown_table,
)


def test_save_markdown_table_creates_file(tmp_path):
    """Verify save_markdown_table creates a new file containing the table."""
    output = tmp_path / "output.md"
    data = {"Name": ["Alice", "Bob"], "Score": [90, 85]}

    save_markdown_table(data, output, "Results")

    assert output.exists()
    content = output.read_text()
    assert "Alice" in content
    assert "Bob" in content
    assert "Score" in content


def test_save_markdown_table_appends(tmp_path):
    """Verify save_markdown_table preserves existing file content when appending."""
    output = tmp_path / "output.md"
    output.write_text("# Existing Header\n\n")

    data = {"Col": ["val"]}
    save_markdown_table(data, output, "New Table")

    content = output.read_text()
    assert content.startswith("# Existing Header\n\n")
    assert "New Table" in content
    assert "val" in content


def test_save_markdown_table_empty_data(tmp_path):
    """Verify save_markdown_table raises ValueError when given an empty dict."""
    output = tmp_path / "output.md"

    with pytest.raises(ValueError, match="empty"):
        save_markdown_table({}, output, "Empty")


def test_save_markdown_table_mismatched_lengths(tmp_path):
    """Verify save_markdown_table raises ValueError when columns have different lengths."""
    output = tmp_path / "output.md"
    data = {"A": [1, 2, 3], "B": [4, 5]}

    with pytest.raises(ValueError, match="mismatch"):
        save_markdown_table(data, output, "Bad Data")


def test_save_markdown_table_format(tmp_path):
    """Verify the output matches GFM table syntax with pipe separators and header rule."""
    output = tmp_path / "output.md"
    data = {"X": [1], "Y": [2]}

    save_markdown_table(data, output, "Format Check")

    lines = output.read_text().strip().splitlines()
    # Find the header row (first pipe-separated line)
    table_lines = [line for line in lines if line.startswith("|")]
    assert len(table_lines) >= 3, "Table must have header, separator, and at least one data row"

    header_row = table_lines[0]
    separator_row = table_lines[1]
    data_row = table_lines[2]

    # Header contains column names separated by pipes
    assert "X" in header_row
    assert "Y" in header_row
    assert header_row.count("|") >= 3

    # Separator row uses --- between pipes
    assert "---" in separator_row

    # Data row contains values
    assert "1" in data_row
    assert "2" in data_row


def test_create_analysis_summary_header(tmp_path):
    """Verify the summary header file contains the metro name, date, and sample size."""
    output = tmp_path / "summary.md"

    create_analysis_summary_header(output, "Phoenix", 42)

    content = output.read_text()
    assert "Phoenix" in content
    assert "42" in content
    assert "Sample Size" in content
    today_str = date.today().strftime("%B %d, %Y")
    assert today_str in content


def test_append_section(tmp_path):
    """Verify append_section writes a ## heading followed by content and a --- separator."""
    output = tmp_path / "report.md"
    output.write_text("# Report\n\n")

    append_section(output, "Findings", "Some analysis results here.")

    content = output.read_text()
    assert "## Findings" in content
    assert "Some analysis results here." in content
    assert "---" in content
    # Ensure original content is preserved
    assert content.startswith("# Report\n\n")
