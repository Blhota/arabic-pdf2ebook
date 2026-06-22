"""List detection from OCR / text-layer lines.

Detects bullet (•, *) and ordered (1. / ١. / 1)) list items, handling both
Latin and Arabic-Indic digits. To avoid mistaking a stray bullet or a numeral
for a list, only runs of two or more consecutive item lines are treated as a
list. Dash markers (-, –, —) are deliberately NOT treated as bullets: Arabic
dialogue and parentheticals routinely begin with a dash, and misreading those
as a list is worse than missing the occasional dash-bulleted list. Text arrives
in logical order, so the marker sits at the line start.
"""

from __future__ import annotations

import re

from ..ocr.base import OcrPage

_BULLET = r"[•‣◦·∙*●▪]"
_UL_RE = re.compile(rf"^\s*{_BULLET}\s+(\S.*)$")
_OL_RE = re.compile(r"^\s*[0-9٠-٩]{1,3}\s*[.)\-]\s+(\S.*)$")


def _item(text: str) -> tuple[str, str] | None:
    """Return (marker_kind, text_without_marker) or None."""
    m = _OL_RE.match(text)
    if m:
        return ("ol", m.group(1).strip())
    m = _UL_RE.match(text)
    if m:
        return ("ul", m.group(1).strip())
    return None


def detect_list_items(page: OcrPage) -> dict[int, tuple[str, str]]:
    """Map non-empty line index → (marker_kind "ul"|"ol", item text)."""
    lines = [ln for ln in page.lines if ln.text.strip()]
    out: dict[int, tuple[str, str]] = {}
    i, n = 0, len(lines)
    while i < n:
        if _item(lines[i].text) is None:
            i += 1
            continue
        j = i
        run: list[tuple[int, tuple[str, str]]] = []
        while j < n:
            item = _item(lines[j].text)
            if item is None:
                break
            run.append((j, item))
            j += 1
        if len(run) >= 2:
            for idx, item in run:
                out[idx] = item
        i = j
    return out
