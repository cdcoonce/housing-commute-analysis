"""Tests for encoding corruption detection in Markdown.

This module tests the detection and fixing of UTF-8 encoding issues
where characters appear corrupted (e.g., Ã— instead of ×).
"""

import pytest

from markdown_analyzer import analyze_markdown
from models import IssueCategory, Severity


class TestEncodingCorruptionDetection:
    """Tests for detecting UTF-8 encoding corruption."""

    def test_detect_multiplication_sign_corruption(self):
        """Test detection of corrupted multiplication sign (Ã— → ×)."""
        content = "# Formula\n\nGeneration \xc3\x97 Contract Price"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050" and "encoding" in i.message.lower()
        ]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0].severity == Severity.ERROR

    def test_detect_checkmark_corruption(self):
        """Test detection of corrupted checkmark (âœ" → ✓)."""
        content = "# Status\n\n| Done | Task |\n|------|------|\n| \xe2\x9c\x93 | Item |"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050" and "encoding" in i.message.lower()
        ]
        assert len(encoding_issues) >= 1

    def test_detect_box_drawing_corruption(self):
        """Test detection of corrupted box-drawing characters."""
        content = "# Diagram\n\n```\n\xe2\x94\x8c\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x90\n\xe2\x94\x82 Box \xe2\x94\x82\n\xe2\x94\x94\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x98\n```"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050" and "encoding" in i.message.lower()
        ]
        assert len(encoding_issues) >= 1

    def test_detect_arrow_corruption(self):
        """Test detection of corrupted arrow symbols (â† → ←)."""
        content = "# Flow\n\nData \xe2\x86\x90 Source"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1

    def test_detect_dash_corruption(self):
        """Test detection of corrupted em-dash (â€" → —)."""
        content = "# Title\n\nThis \xe2\x80\x94 that"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1

    def test_detect_bullet_corruption(self):
        """Test detection of corrupted bullet points (â€¢ → •)."""
        content = "# List\n\n\xe2\x80\xa2 Item one\n\xe2\x80\xa2 Item two"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1

    def test_no_false_positives_clean_content(self):
        """Test that clean content doesn't trigger encoding issues."""
        content = "# Clean Document\n\nThis is normal text with proper Unicode."
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) == 0

    def test_suggested_fix_provided(self):
        """Test that encoding issues have suggested fixes."""
        content = "# Formula\n\nValue \xc3\x97 10"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0].suggested_fix is not None
        # The fix should contain the proper character (×)
        assert "×" in encoding_issues[0].suggested_fix.fixed_code

    def test_multiple_corruptions_same_line(self):
        """Test detection of multiple corruptions on same line."""
        # A × B → C (multiplication and arrow)
        content = "# Math\n\nA \xc3\x97 B \xe2\x86\x92 C"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        # Should find corruptions (at least one per line)
        assert len(encoding_issues) >= 1

    def test_corruption_in_table(self):
        """Test detection of corruption in markdown tables."""
        content = """# Revenue

| Component | Formula |
|-----------|---------|
| Revenue | Generation \xc3\x97 Price |
| Cost | Hub \xe2\x80\x94 Node |
"""
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1

    def test_fix_is_auto_fixable(self):
        """Test that encoding fixes are marked as auto-fixable."""
        content = "# Test\n\nDone \xe2\x9c\x93"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0].suggested_fix is not None
        assert encoding_issues[0].suggested_fix.auto_fixable is True


class TestEncodingCorruptionPatterns:
    """Tests for specific encoding corruption patterns."""

    def test_multiplication_pattern(self):
        """Test multiplication sign corruption."""
        content = "# Test\n\nText with \xc3\x97 symbol"  # Ã—
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_division_pattern(self):
        """Test division sign corruption."""
        content = "# Test\n\nText with \xc3\xb7 symbol"  # Ã·
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_copyright_pattern(self):
        """Test copyright sign corruption."""
        content = "# Test\n\nText with \xc2\xa9 symbol"  # Â©
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_registered_pattern(self):
        """Test registered sign corruption."""
        content = "# Test\n\nText with \xc2\xae symbol"  # Â®
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_box_drawing_patterns(self):
        """Test box-drawing character corruption patterns."""
        # Box drawing: ┌── (corrupted as â"Œâ"€â"€)
        content = "# Diagram\n\n```\n\xe2\x94\x8c\xe2\x94\x80\xe2\x94\x80\n```"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1


class TestEncodingFixApplication:
    """Tests for applying encoding fixes."""

    def test_fix_replaces_corruption(self):
        """Test that the fix correctly replaces corrupted text."""
        content = "# Formula\n\nGeneration \xc3\x97 Contract Price"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1

        fix = encoding_issues[0].suggested_fix
        assert fix is not None
        # The fixed code should contain the proper multiplication sign
        assert "×" in fix.fixed_code
        # And not contain the corrupted sequence
        assert "\xc3\x97" not in fix.fixed_code

    def test_context_shows_corrupted_line(self):
        """Test that issue context shows the corrupted line."""
        content = "# Test\n\nBad line with \xc3\x97 here"
        result = analyze_markdown(content)

        encoding_issues = [
            i for i in result.issues
            if i.rule_id == "MD050"
        ]
        assert len(encoding_issues) >= 1
        assert encoding_issues[0].context is not None
        # Context should contain the original corrupted text
        assert "\xc3\x97" in encoding_issues[0].context


class TestRealWorldCorruption:
    """Tests based on real-world corruption examples."""

    def test_table_with_multiplication(self):
        """Test table with corrupted multiplication signs (from user example)."""
        content = """# Revenue Components

| Revenue Component | Formula | When It Applies |
|-------------------|---------|-----------------|
| Contract Revenue | Generation \xc3\x97 Contract Price | Fixed-price PPAs |
| Merchant Revenue | Generation \xc3\x97 Spot Price | Uncontracted energy |
| Basis Cost | (Hub Price - Node Price) \xc3\x97 Generation | VPPAs |
"""
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1
        # Each row with Ã— should be detected
        assert len(encoding_issues) >= 3

    def test_formula_calculation(self):
        """Test corrupted formula calculation (from user example)."""
        content = """# Example Calculation

Swap Settlement = (Fixed \xe2\x80\x94 Index) \xc3\x97 Volume
               = ($45 \xe2\x80\x94 $38) \xc3\x97 10,000
               = $70,000
"""
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_enterprise_matrix_checkmarks(self):
        """Test table with corrupted checkmarks (from user example)."""
        content = """# Enterprise Bus Matrix

| Business Process | Facility | Date |
|------------------|----------|------|
| Daily Generation | \xe2\x9c\x93 | \xe2\x9c\x93 |
| Hourly Basis | \xe2\x9c\x93 | \xe2\x9c\x93 |
"""
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        assert len(encoding_issues) >= 1

    def test_box_diagram(self):
        """Test corrupted ASCII box diagram (from user example)."""
        content = """# MCP Protocol Layers

```
\xe2\x94\x8c\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x90
\xe2\x94\x82   Application    \xe2\x94\x82  \xe2\x86\x90 Claude
\xe2\x94\x9c\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\xa4
\xe2\x94\x82   MCP Client     \xe2\x94\x82
\xe2\x94\x94\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x98
```
"""
        result = analyze_markdown(content)
        encoding_issues = [i for i in result.issues if i.rule_id == "MD050"]
        # Should detect box drawing corruption
        assert len(encoding_issues) >= 1
