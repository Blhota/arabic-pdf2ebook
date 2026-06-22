"""Chapter heading detection — a thin wrapper over textproc.headings.

Heading classification (including font-size tiers) now lives in
`textproc.headings`; this module keeps the historical `detect_heading_lines`
entry point and re-exports the heading helpers for existing callers/tests.
"""

from __future__ import annotations

from ..ocr.base import OcrPage
from .headings import (
    HEADING_WORD_RE,
    MAX_HEADING_WORDS,
    heading_tiers,
    looks_like_heading_text,
)

__all__ = [
    "HEADING_WORD_RE",
    "MAX_HEADING_WORDS",
    "looks_like_heading_text",
    "heading_tiers",
    "detect_heading_lines",
]


def detect_heading_lines(page: OcrPage) -> list[int]:
    """Indices of lines on this page that look like chapter headings."""
    return sorted(heading_tiers(page).keys())
