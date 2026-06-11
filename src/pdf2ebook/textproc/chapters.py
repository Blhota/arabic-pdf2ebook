"""Chapter detection: visual heading heuristics with a per-N-pages fallback."""

from __future__ import annotations

import re
from statistics import median

from ..ocr.base import OcrPage

HEADING_WORD_RE = re.compile(
    r"^\s*(الباب|الفصل|باب|فصل|مقدمة|المقدمة|تمهيد|خاتمة|الخاتمة|فهرس|المراجع|ملحق)"
)
MAX_HEADING_WORDS = 8


def looks_like_heading_text(text: str) -> bool:
    words = text.split()
    return bool(words) and len(words) <= MAX_HEADING_WORDS and bool(HEADING_WORD_RE.match(text))


def detect_heading_lines(page: OcrPage) -> list[int]:
    """Indices of lines on this page that look like chapter headings."""
    lines = [ln for ln in page.lines if ln.text.strip()]
    if not lines:
        return []
    med_height = median(ln.bbox[3] for ln in lines)
    page_width = page.size[0] or 1
    out: list[int] = []
    for i, ln in enumerate(lines):
        text = ln.text.strip()
        words = len(text.split())
        if not text or words > MAX_HEADING_WORDS:
            continue
        tall = med_height > 0 and ln.bbox[3] > 1.35 * med_height
        center = ln.bbox[0] + ln.bbox[2] / 2
        centered = abs(center - page_width / 2) < page_width * 0.12
        keyword = bool(HEADING_WORD_RE.match(text))
        if (tall and centered) or (keyword and centered) or (keyword and tall):
            out.append(i)
    return out
