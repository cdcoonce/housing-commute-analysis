"""
Reporting and output utilities for DAT490 analysis.

This module handles markdown table generation and results reporting.
"""

import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def save_markdown_table(
    data: Dict[str, List],
    path: Path,
    title: str
) -> None:
    """
    Append a formatted markdown table to an existing file.
    
    Converts dictionary data to GitHub-flavored markdown table format with
    aligned columns. Appends to existing file rather than overwriting.
    
    Parameters
    ----------
    data : Dict[str, List]
        Dictionary mapping column names (str) to column values (List).
        All lists must have the same length.
    path : Path
        Output markdown file path. File is created if it doesn't exist,
        or appended to if it exists.
    title : str
        Table section title (rendered as ### heading).
    
    Returns
    -------
    None
        Appends markdown table to file at path.
    
    Raises
    ------
    ValueError
        If data dictionary is empty or if column lists have inconsistent lengths.
    
    Notes
    -----
    - Uses pipe-separated GitHub-flavored markdown table syntax
    - All values are converted to strings via str()
    - File is opened in append mode ('a'), preserving existing content
    """
    # Validate data structure before generating table
    if not data:
        raise ValueError("Data dictionary cannot be empty")
    
    # Check all columns have same length to prevent malformed tables
    column_lengths = [len(values) for values in data.values()]
    if len(set(column_lengths)) > 1:
        raise ValueError(
            f"Column length mismatch: {dict(zip(data.keys(), column_lengths))}. "
            "All columns must have the same number of rows."
        )
    
    # Ensure parent directory exists and path is safe
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Validate path to prevent directory traversal attacks
    try:
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid file path: {path}. {e}") from e
    
    with open(resolved_path, 'a', encoding='utf-8') as f:
        f.write(f"\n### {title}\n\n")
        
        # Header
        headers = list(data.keys())
        f.write("| " + " | ".join(headers) + " |\n")
        f.write("| " + " | ".join(["---"] * len(headers)) + " |\n")
        
        # Rows
        n_rows = len(data[headers[0]])
        for i in range(n_rows):
            row = [str(data[col][i]) for col in headers]
            f.write("| " + " | ".join(row) + " |\n")
        
        f.write("\n")
    
    logger.info(f"Saved table '{title}' to {path}")


def create_analysis_summary_header(
    path: Path,
    metro_name: str,
    sample_size: int
) -> None:
    """
    Create header section for a metro-specific analysis summary markdown file.
    
    Initializes a new markdown file with standardized header containing metro name,
    analysis date, and sample size. Overwrites existing file if present.
    
    Parameters
    ----------
    path : Path
        Output file path for markdown summary (e.g., "analysis_summary_phx.md").
    metro_name : str
        Full metropolitan area name (e.g., "Phoenix", "Los Angeles").
    sample_size : int
        Number of ZCTAs included in analysis.
    
    Returns
    -------
    None
        Creates new markdown file with header content.
    
    Notes
    -----
    File is opened in write mode ('w'), which overwrites existing content.
    Use this function only to initialize new summary files.
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Validate path to prevent directory traversal attacks
    try:
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid file path: {path}. {e}") from e
    
    with open(resolved_path, 'w', encoding='utf-8') as f:
        f.write(f"# DAT490 Analysis Summary: {metro_name}\n\n")
        f.write("Analysis Date: November 9, 2025\n\n")
        f.write(f"Sample Size: {sample_size} ZCTAs\n\n")
        f.write("---\n\n")
    
    logger.info(f"Created analysis summary header at {resolved_path}")


def append_section(
    path: Path,
    title: str,
    content: str
) -> None:
    """
    Append a titled section with horizontal rule separator to markdown file.
    
    Adds a new section to an existing markdown file with ## heading, content body,
    and visual separator (---). Preserves existing file content.
    
    Parameters
    ----------
    path : Path
        Markdown file path to append to.
    title : str
        Section title (rendered as ## heading).
    content : str
        Section body content (plain text or markdown).
    
    Returns
    -------
    None
        Appends section to file at path.
    
    Notes
    -----
    File must exist before calling this function. Use create_analysis_summary_header()
    to initialize new files.
    """
    # Validate path to prevent directory traversal attacks
    try:
        resolved_path = path.resolve(strict=False)
    except (OSError, RuntimeError) as e:
        raise ValueError(f"Invalid file path: {path}. {e}") from e
    
    with open(resolved_path, 'a', encoding='utf-8') as f:
        f.write(f"## {title}\n\n")
        f.write(content)
        f.write("\n\n---\n\n")
    
    logger.info(f"Appended section '{title}' to {resolved_path}")
