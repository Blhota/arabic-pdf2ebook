"""Paragraph reconstruction from OCR lines.

Arabic is RTL: a paragraph-opening indent shows as the line's *right* edge
being inset from the text block's right margin. Joins use plain spaces —
Arabic does not hyphenate across lines.
"""

from __future__ import annotations

from statistics import median

from ..ocr.base import OcrPage
from .dehyphen import join_wrapped

TERMINAL_PUNCT = ".؟!:»۔"  # Arabic question mark lives at ؟ = ؟


def page_paragraphs(page: OcrPage) -> list[str]:
    """Group a page's OCR lines into paragraph strings."""
    lines = [ln for ln in page.lines if ln.text.strip()]
    if not lines:
        return []

    gaps = []
    for prev, cur in zip(lines, lines[1:]):
        gaps.append(max(0, cur.bbox[1] - (prev.bbox[1] + prev.bbox[3])))
    med_gap = median(gaps) if gaps else 0
    right_edges = [ln.bbox[0] + ln.bbox[2] for ln in lines]
    block_right = max(right_edges)
    med_height = median(ln.bbox[3] for ln in lines) or 1

    paragraphs: list[list[str]] = [[lines[0].text]]
    for i in range(1, len(lines)):
        prev, cur = lines[i - 1], lines[i]
        gap = max(0, cur.bbox[1] - (prev.bbox[1] + prev.bbox[3]))
        big_gap = med_gap > 0 and gap > 1.8 * med_gap
        # RTL indent: current line starts (right edge) noticeably inside the margin.
        cur_right = cur.bbox[0] + cur.bbox[2]
        indented = (block_right - cur_right) > 1.2 * med_height
        prev_text = prev.text.strip()
        prev_terminated = bool(prev_text) and prev_text[-1] in TERMINAL_PUNCT
        prev_short = (prev.bbox[2]) < 0.7 * (max(right_edges) - min(ln.bbox[0] for ln in lines))

        if big_gap or (indented and (prev_terminated or prev_short)) or (prev_terminated and prev_short):
            paragraphs.append([cur.text])
        else:
            paragraphs[-1].append(cur.text)

    joined = [join_wrapped(chunk) for chunk in paragraphs]
    return [p for p in joined if p]


def merge_page_boundary(prev_paragraphs: list[str], next_paragraphs: list[str]) -> tuple[list[str], list[str]]:
    """Join a paragraph that continues across a page break."""
    if not prev_paragraphs or not next_paragraphs:
        return prev_paragraphs, next_paragraphs
    last = prev_paragraphs[-1].rstrip()
    if last and last[-1] not in TERMINAL_PUNCT:
        merged = last + " " + next_paragraphs[0].lstrip()
        return prev_paragraphs[:-1] + [merged], next_paragraphs[1:]
    return prev_paragraphs, next_paragraphs
