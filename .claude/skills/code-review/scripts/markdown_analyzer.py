"""Markdown documentation analyzer.

This module provides functionality to analyze Markdown files for quality issues
including broken links, heading structure, common formatting problems, and
UTF-8 encoding corruption detection.
"""

import re
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


# Regex patterns for Markdown analysis
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
LINK_PATTERN = re.compile(r"\[([^\]]*)\]\(([^)]*)\)")
IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
REFERENCE_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\[([^\]]*)\]")
REFERENCE_DEF_PATTERN = re.compile(r"^\[([^\]]+)\]:\s*(.+)$", re.MULTILINE)
CODE_BLOCK_PATTERN = re.compile(r"```(\w*)\n(.*?)```", re.DOTALL)
INLINE_CODE_PATTERN = re.compile(r"`([^`]+)`")
TRAILING_WHITESPACE_PATTERN = re.compile(r"[ \t]+$", re.MULTILINE)
MULTIPLE_BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
DUPLICATE_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


# UTF-8 encoding corruption patterns
# These occur when UTF-8 bytes are misinterpreted as Latin-1/Windows-1252
ENCODING_CORRUPTION_MAP: dict[str, str] = {
    # Mathematical symbols
    "\xc3\x97": "×",  # multiplication sign
    "\xc3\xb7": "÷",  # division sign
    "\xc2\xb1": "±",  # plus-minus
    "\xc2\xb0": "°",  # degree
    "\xc2\xb5": "µ",  # micro
    # Comparison operators
    "\xe2\x89\xa0": "≠",  # not equal (â‰ )
    "\xe2\x89\xa4": "≤",  # less than or equal (â‰¤)
    "\xe2\x89\xa5": "≥",  # greater than or equal (â‰¥)
    "\xe2\x89\x88": "≈",  # approximately (â‰ˆ)
    # Arrows
    "\xe2\x86\x90": "←",  # left arrow (â†)
    "\xe2\x86\x92": "→",  # right arrow (â†')
    "\xe2\x86\x91": "↑",  # up arrow (â†')
    "\xe2\x86\x93": "↓",  # down arrow (â†")
    "\xe2\x86\x94": "↔",  # left-right arrow
    "\xe2\x87\x90": "⇐",  # left double arrow
    "\xe2\x87\x92": "⇒",  # right double arrow
    # Dashes and punctuation
    "\xe2\x80\x94": "—",  # em dash (â€")
    "\xe2\x80\x93": "–",  # en dash (â€")
    "\xe2\x80\xa2": "•",  # bullet (â€¢)
    "\xe2\x80\xa6": "…",  # ellipsis (â€¦)
    "\xe2\x80\x98": "'",  # left single quote
    "\xe2\x80\x99": "'",  # right single quote
    "\xe2\x80\x9c": """,  # left double quote
    "\xe2\x80\x9d": """,  # right double quote
    # Checkmarks and symbols
    "\xe2\x9c\x93": "✓",  # checkmark (âœ")
    "\xe2\x9c\x94": "✔",  # heavy checkmark (âœ")
    "\xe2\x9c\x97": "✗",  # ballot x (âœ—)
    "\xe2\x9c\x98": "✘",  # heavy ballot x
    "\xe2\x9c\x85": "✅",  # white heavy check mark
    "\xe2\x9d\x8c": "❌",  # cross mark
    # Legal/trademark symbols
    "\xc2\xa9": "©",  # copyright (Â©)
    "\xc2\xae": "®",  # registered (Â®)
    "\xe2\x84\xa2": "™",  # trademark (â„¢)
    # Currency
    "\xe2\x82\xac": "€",  # euro (â‚¬)
    "\xc2\xa3": "£",  # pound (Â£)
    "\xc2\xa5": "¥",  # yen (Â¥)
    # Box drawing characters
    "\xe2\x94\x80": "─",  # horizontal (â"€)
    "\xe2\x94\x82": "│",  # vertical (â"‚)
    "\xe2\x94\x8c": "┌",  # top-left (â"Œ)
    "\xe2\x94\x90": "┐",  # top-right (â"")
    "\xe2\x94\x94": "└",  # bottom-left (â"")
    "\xe2\x94\x98": "┘",  # bottom-right (â"˜)
    "\xe2\x94\x9c": "├",  # left-tee (â"œ)
    "\xe2\x94\xa4": "┤",  # right-tee (â"¤)
    "\xe2\x94\xac": "┬",  # top-tee (â"¬)
    "\xe2\x94\xb4": "┴",  # bottom-tee (â"´)
    "\xe2\x94\xbc": "┼",  # cross (â"¼)
    "\xe2\x95\x90": "═",  # double horizontal
    "\xe2\x95\x91": "║",  # double vertical
    "\xe2\x95\x94": "╔",  # double top-left
    "\xe2\x95\x97": "╗",  # double top-right
    "\xe2\x95\x9a": "╚",  # double bottom-left
    "\xe2\x95\x9d": "╝",  # double bottom-right
    # Fractions
    "\xc2\xbd": "½",  # one half
    "\xc2\xbc": "¼",  # one quarter
    "\xc2\xbe": "¾",  # three quarters
    # Superscripts
    "\xc2\xb2": "²",  # superscript 2
    "\xc2\xb3": "³",  # superscript 3
    # Other common
    "\xc2\xa0": " ",  # non-breaking space (often invisible issue)
    "\xc2\xab": "«",  # left guillemet
    "\xc2\xbb": "»",  # right guillemet
    "\xc2\xa7": "§",  # section sign
    "\xc2\xb6": "¶",  # pilcrow
}

# Build a regex pattern that matches any of the corrupted sequences
# Sort by length (longest first) to match longer sequences first
_sorted_corruptions = sorted(ENCODING_CORRUPTION_MAP.keys(), key=len, reverse=True)
ENCODING_CORRUPTION_PATTERN = re.compile(
    "|".join(re.escape(seq) for seq in _sorted_corruptions)
)


class MarkdownAnalyzer:
    """Analyzer for Markdown documentation files.

    This class performs various quality checks on Markdown content including
    heading structure validation, link checking, and formatting issues.

    Parameters
    ----------
    base_path : Optional[Path]
        Base path for resolving relative file links.

    Attributes
    ----------
    base_path : Optional[Path]
        The base path for relative link resolution.
    """

    def __init__(self, base_path: Optional[Path] = None) -> None:
        """Initialize the Markdown analyzer.

        Parameters
        ----------
        base_path : Optional[Path]
            Base path for resolving relative file links.
        """
        self.base_path = base_path

    def analyze(
        self,
        content: str,
        file_path: Optional[Path] = None,
    ) -> AnalysisResult:
        """Analyze Markdown content for quality issues.

        Parameters
        ----------
        content : str
            The Markdown content to analyze.
        file_path : Optional[Path]
            Path to the source file for location reporting.

        Returns
        -------
        AnalysisResult
            The analysis results containing all found issues.
        """
        start_time = time.time()
        issues: list[Issue] = []
        lines = content.splitlines()

        # Run all checks
        issues.extend(self._check_heading_structure(content, lines, file_path))
        issues.extend(self._check_heading_levels(content, lines, file_path))
        issues.extend(self._check_duplicate_headings(content, lines, file_path))
        issues.extend(self._check_links(content, lines, file_path))
        issues.extend(self._check_images(content, lines, file_path))
        issues.extend(self._check_reference_links(content, lines, file_path))
        issues.extend(self._check_formatting(content, lines, file_path))
        issues.extend(self._check_code_blocks(content, lines, file_path))
        issues.extend(self._check_encoding_corruption(content, lines, file_path))

        elapsed = time.time() - start_time

        return AnalysisResult(
            file_type=FileType.MARKDOWN,
            source_path=file_path,
            issues=issues,
            source_content=content,
            analysis_time_seconds=elapsed,
            tools_used=["markdown-analyzer"],
        )

    def _find_line_number(self, content: str, match_start: int) -> int:
        """Find the line number for a given character position.

        Parameters
        ----------
        content : str
            The full content string.
        match_start : int
            Character position in the content.

        Returns
        -------
        int
            The 1-indexed line number.
        """
        return content[:match_start].count("\n") + 1

    def _check_heading_structure(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for proper heading structure.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of heading structure issues.
        """
        issues: list[Issue] = []
        headings = list(HEADING_PATTERN.finditer(content))

        if not headings:
            return issues

        # Check for document starting with h1
        first_heading = headings[0]
        if len(first_heading.group(1)) != 1:
            line_num = self._find_line_number(content, first_heading.start())
            issues.append(
                Issue(
                    severity=Severity.WARNING,
                    category=IssueCategory.MARKDOWN,
                    message="Document should start with a level 1 heading (h1)",
                    location=Location(file_path=file_path, line_start=line_num),
                    rule_id="MD041",
                    source="markdown-analyzer",
                    context=first_heading.group(0),
                    suggested_fix=SuggestedFix(
                        description="Add or change to level 1 heading",
                        original_code=first_heading.group(0),
                        fixed_code=f"# {first_heading.group(2)}",
                        auto_fixable=True,
                    ),
                )
            )

        # Check for multiple h1 headings
        h1_headings = [h for h in headings if len(h.group(1)) == 1]
        if len(h1_headings) > 1:
            for h1 in h1_headings[1:]:
                line_num = self._find_line_number(content, h1.start())
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        category=IssueCategory.MARKDOWN,
                        message="Multiple level 1 headings found; document should have only one",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD025",
                        source="markdown-analyzer",
                        context=h1.group(0),
                        suggested_fix=SuggestedFix(
                            description="Change to level 2 heading",
                            original_code=h1.group(0),
                            fixed_code=f"## {h1.group(2)}",
                            auto_fixable=True,
                        ),
                    )
                )

        return issues

    def _check_heading_levels(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for skipped heading levels.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of heading level issues.
        """
        issues: list[Issue] = []
        headings = list(HEADING_PATTERN.finditer(content))

        prev_level = 0
        for heading in headings:
            level = len(heading.group(1))
            if prev_level > 0 and level > prev_level + 1:
                line_num = self._find_line_number(content, heading.start())
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        category=IssueCategory.MARKDOWN,
                        message=f"Heading level skipped from h{prev_level} to h{level}",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD001",
                        source="markdown-analyzer",
                        context=heading.group(0),
                        suggested_fix=SuggestedFix(
                            description=f"Change to level {prev_level + 1} heading",
                            original_code=heading.group(0),
                            fixed_code=f"{'#' * (prev_level + 1)} {heading.group(2)}",
                            auto_fixable=True,
                        ),
                    )
                )
            prev_level = level

        return issues

    def _check_duplicate_headings(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for duplicate headings at the same level.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of duplicate heading issues.
        """
        issues: list[Issue] = []
        headings = list(HEADING_PATTERN.finditer(content))

        seen_headings: dict[str, int] = {}
        for heading in headings:
            heading_text = heading.group(2).strip().lower()
            if heading_text in seen_headings:
                line_num = self._find_line_number(content, heading.start())
                issues.append(
                    Issue(
                        severity=Severity.INFO,
                        category=IssueCategory.MARKDOWN,
                        message=f"Duplicate heading '{heading.group(2)}' (first at line {seen_headings[heading_text]})",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD024",
                        source="markdown-analyzer",
                        context=heading.group(0),
                    )
                )
            else:
                seen_headings[heading_text] = self._find_line_number(
                    content, heading.start()
                )

        return issues

    def _check_links(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for link issues.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of link issues.
        """
        issues: list[Issue] = []

        for match in LINK_PATTERN.finditer(content):
            link_text = match.group(1)
            link_url = match.group(2)
            line_num = self._find_line_number(content, match.start())

            # Check for empty link text
            if not link_text.strip():
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        category=IssueCategory.MARKDOWN,
                        message="Link has empty text",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD045",
                        source="markdown-analyzer",
                        context=match.group(0),
                    )
                )

            # Check for empty URLs
            if not link_url.strip():
                issues.append(
                    Issue(
                        severity=Severity.ERROR,
                        category=IssueCategory.MARKDOWN,
                        message="Link has empty URL",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD042",
                        source="markdown-analyzer",
                        context=match.group(0),
                    )
                )

            # Check for relative file links that might be broken
            if (
                self.base_path
                and not link_url.startswith(("http://", "https://", "#", "mailto:"))
                and not link_url.startswith("/")
            ):
                # Remove anchor from URL for file check
                file_url = link_url.split("#")[0]
                if file_url:
                    target_path = self.base_path / file_url
                    if not target_path.exists():
                        issues.append(
                            Issue(
                                severity=Severity.ERROR,
                                category=IssueCategory.MARKDOWN,
                                message=f"Broken link: file '{file_url}' not found",
                                location=Location(
                                    file_path=file_path, line_start=line_num
                                ),
                                rule_id="MD052",
                                source="markdown-analyzer",
                                context=match.group(0),
                            )
                        )

        return issues

    def _check_images(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for image issues.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of image issues.
        """
        issues: list[Issue] = []

        for match in IMAGE_PATTERN.finditer(content):
            alt_text = match.group(1)
            image_url = match.group(2)
            line_num = self._find_line_number(content, match.start())

            # Check for missing alt text
            if not alt_text.strip():
                issues.append(
                    Issue(
                        severity=Severity.WARNING,
                        category=IssueCategory.MARKDOWN,
                        message="Image missing alt text (accessibility issue)",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD045",
                        source="markdown-analyzer",
                        context=match.group(0),
                    )
                )

            # Check for broken image links
            if (
                self.base_path
                and not image_url.startswith(("http://", "https://", "data:"))
            ):
                target_path = self.base_path / image_url
                if not target_path.exists():
                    issues.append(
                        Issue(
                            severity=Severity.ERROR,
                            category=IssueCategory.MARKDOWN,
                            message=f"Broken image: file '{image_url}' not found",
                            location=Location(
                                file_path=file_path, line_start=line_num
                            ),
                            rule_id="MD053",
                            source="markdown-analyzer",
                            context=match.group(0),
                        )
                    )

        return issues

    def _check_reference_links(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for undefined reference links.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of reference link issues.
        """
        issues: list[Issue] = []

        # Find all reference definitions
        defined_refs = {
            m.group(1).lower() for m in REFERENCE_DEF_PATTERN.finditer(content)
        }

        # Check all reference links
        for match in REFERENCE_LINK_PATTERN.finditer(content):
            ref_id = match.group(2) if match.group(2) else match.group(1)
            if ref_id.lower() not in defined_refs:
                line_num = self._find_line_number(content, match.start())
                issues.append(
                    Issue(
                        severity=Severity.ERROR,
                        category=IssueCategory.MARKDOWN,
                        message=f"Undefined reference link: '{ref_id}'",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD052",
                        source="markdown-analyzer",
                        context=match.group(0),
                    )
                )

        return issues

    def _check_formatting(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for formatting issues.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of formatting issues.
        """
        issues: list[Issue] = []

        # Check for trailing whitespace
        for match in TRAILING_WHITESPACE_PATTERN.finditer(content):
            line_num = self._find_line_number(content, match.start())
            # Skip if it's an intentional line break (2 spaces)
            if len(match.group(0)) != 2:
                issues.append(
                    Issue(
                        severity=Severity.INFO,
                        category=IssueCategory.MARKDOWN,
                        message="Trailing whitespace",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD009",
                        source="markdown-analyzer",
                        suggested_fix=SuggestedFix(
                            description="Remove trailing whitespace",
                            original_code=lines[line_num - 1] if lines else "",
                            fixed_code=lines[line_num - 1].rstrip() if lines else "",
                            auto_fixable=True,
                        ),
                    )
                )

        # Check for multiple consecutive blank lines
        for match in MULTIPLE_BLANK_LINES_PATTERN.finditer(content):
            line_num = self._find_line_number(content, match.start())
            issues.append(
                Issue(
                    severity=Severity.INFO,
                    category=IssueCategory.MARKDOWN,
                    message="Multiple consecutive blank lines",
                    location=Location(file_path=file_path, line_start=line_num),
                    rule_id="MD012",
                    source="markdown-analyzer",
                    suggested_fix=SuggestedFix(
                        description="Reduce to single blank line",
                        original_code=match.group(0),
                        fixed_code="\n\n",
                        auto_fixable=True,
                    ),
                )
            )

        # Check for missing blank line after heading
        for i, line in enumerate(lines):
            if HEADING_PATTERN.match(line):
                if i + 1 < len(lines) and lines[i + 1].strip():
                    issues.append(
                        Issue(
                            severity=Severity.INFO,
                            category=IssueCategory.MARKDOWN,
                            message="Missing blank line after heading",
                            location=Location(file_path=file_path, line_start=i + 1),
                            rule_id="MD022",
                            source="markdown-analyzer",
                            context=line,
                        )
                    )

        return issues

    def _check_code_blocks(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for code block issues.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of code block issues.
        """
        issues: list[Issue] = []

        for match in CODE_BLOCK_PATTERN.finditer(content):
            language = match.group(1)
            line_num = self._find_line_number(content, match.start())

            # Check for missing language identifier
            if not language:
                issues.append(
                    Issue(
                        severity=Severity.INFO,
                        category=IssueCategory.MARKDOWN,
                        message="Code block missing language identifier",
                        location=Location(file_path=file_path, line_start=line_num),
                        rule_id="MD040",
                        source="markdown-analyzer",
                        context="```",
                    )
                )

        return issues

    def _check_encoding_corruption(
        self,
        content: str,
        lines: list[str],
        file_path: Optional[Path],
    ) -> list[Issue]:
        """Check for UTF-8 encoding corruption.

        Detects common patterns where UTF-8 bytes have been misinterpreted
        as Latin-1/Windows-1252, resulting in garbled characters like
        Ã— instead of × or â€" instead of —.

        Parameters
        ----------
        content : str
            The Markdown content.
        lines : list[str]
            Lines of the content.
        file_path : Optional[Path]
            Path to the source file.

        Returns
        -------
        list[Issue]
            List of encoding corruption issues.
        """
        issues: list[Issue] = []
        seen_lines: set[int] = set()  # Track lines already reported

        for match in ENCODING_CORRUPTION_PATTERN.finditer(content):
            corrupted = match.group(0)
            fixed = ENCODING_CORRUPTION_MAP.get(corrupted, "")
            line_num = self._find_line_number(content, match.start())

            # Only report one issue per line to avoid spam
            if line_num in seen_lines:
                continue
            seen_lines.add(line_num)

            # Get the full line for context
            line_content = lines[line_num - 1] if 0 < line_num <= len(lines) else ""

            # Fix the entire line
            fixed_line = line_content
            for corr, fix in ENCODING_CORRUPTION_MAP.items():
                fixed_line = fixed_line.replace(corr, fix)

            # Describe what was found
            if corrupted in ("\xc3\x97",):
                char_desc = "multiplication sign (×)"
            elif corrupted in ("\xc3\xb7",):
                char_desc = "division sign (÷)"
            elif corrupted.startswith("\xe2\x86"):
                char_desc = "arrow symbol"
            elif corrupted.startswith("\xe2\x80\x94") or corrupted.startswith(
                "\xe2\x80\x93"
            ):
                char_desc = "dash character"
            elif corrupted.startswith("\xe2\x80\xa2"):
                char_desc = "bullet point (•)"
            elif corrupted.startswith("\xe2\x9c"):
                char_desc = "checkmark symbol"
            elif corrupted.startswith("\xe2\x94") or corrupted.startswith("\xe2\x95"):
                char_desc = "box-drawing character"
            elif corrupted in ("\xc2\xa9",):
                char_desc = "copyright symbol (©)"
            elif corrupted in ("\xc2\xae",):
                char_desc = "registered symbol (®)"
            elif corrupted.startswith("\xe2\x84"):
                char_desc = "trademark symbol (™)"
            else:
                char_desc = f"character '{fixed}'"

            issues.append(
                Issue(
                    severity=Severity.ERROR,
                    category=IssueCategory.MARKDOWN,
                    message=f"Encoding corruption detected: corrupted {char_desc}",
                    location=Location(file_path=file_path, line_start=line_num),
                    rule_id="MD050",
                    source="markdown-analyzer",
                    context=line_content,
                    suggested_fix=SuggestedFix(
                        description=f"Fix encoding corruption ({char_desc})",
                        original_code=line_content,
                        fixed_code=fixed_line,
                        auto_fixable=True,
                    ),
                )
            )

        return issues


def analyze_markdown(
    content: str,
    file_path: Optional[Path] = None,
    base_path: Optional[Path] = None,
) -> AnalysisResult:
    """Analyze Markdown content for quality issues.

    Parameters
    ----------
    content : str
        The Markdown content to analyze.
    file_path : Optional[Path]
        Path to the source file for location reporting.
    base_path : Optional[Path]
        Base path for resolving relative file links.

    Returns
    -------
    AnalysisResult
        The analysis results containing all found issues.

    Examples
    --------
    >>> result = analyze_markdown("# Title\\n\\nSome content")
    >>> result.file_type == FileType.MARKDOWN
    True
    """
    analyzer = MarkdownAnalyzer(base_path=base_path)
    return analyzer.analyze(content, file_path)


def analyze_markdown_file(file_path: Path) -> AnalysisResult:
    """Analyze a Markdown file for quality issues.

    Parameters
    ----------
    file_path : Path
        Path to the Markdown file to analyze.

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

    content = file_path.read_text(encoding="utf-8")
    return analyze_markdown(content, file_path, base_path=file_path.parent)
