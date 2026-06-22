"""In-memory Markdown pivot: structured elements ⇄ Book.

The conversion routes everything through a clean Markdown string that lives
only in memory (it is never written to disk). Structuring already happened
upstream, so Markdown here is a faithful serialization of typed
`(kind, text)` elements, parsed straight back into the Book model.

Internal conventions (we emit and parse both ends):
    # / ## / ###            headings h1 / h2 / h3
    plain line              paragraph
    - text                  unordered list item
    1. text                 ordered list item
    :::verse … :::          poetry block (one bayt per line)
    :::quran … :::          Quranic quote block
    ![scan](scans/…png)     a page kept as an image
    <!-- page:N -->         source page boundary (0-based)
A paragraph whose text would collide with a marker is backslash-escaped.
"""

from __future__ import annotations

import re

from ..book import Book, Chapter, PageImage, Paragraph
from . import clean

Element = tuple[str, str]

_PAGE_RE = re.compile(r"^<!--\s*page:(\d+)\s*-->$")
_SCAN_RE = re.compile(r"^!\[scan\]\((.+)\)$")
_OL_RE = re.compile(r"^[0-9٠-٩]{1,3}[.)]\s+(.*)$")
_NEEDS_ESCAPE = re.compile(r"^(#{1,6}\s|-\s|[0-9٠-٩]{1,3}[.)]\s|:::|<!--|!\[scan\]\(|\\)")

_HEAD_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### "}
_HEAD_LEVEL = {"h1": 1, "h2": 2, "h3": 3}


# ---------------------------------------------------------------------------
# Emit (elements → Markdown lines)
# ---------------------------------------------------------------------------

def emit_page_break(page_no: int) -> str:
    return f"<!-- page:{page_no} -->"


def emit_scan(image_rel: str) -> str:
    return f"![scan]({image_rel})"


def emit_elements(elements: list[Element]) -> list[str]:
    lines: list[str] = []
    i, n = 0, len(elements)
    while i < n:
        kind, text = elements[i]
        if kind in ("verse", "quran"):
            lines.append(f":::{kind}")
            j = i
            while j < n and elements[j][0] == kind:
                lines.append(elements[j][1])
                j += 1
            lines.append(":::")
            i = j
            continue
        if kind in _HEAD_PREFIX:
            lines.append(_HEAD_PREFIX[kind] + text)
        elif kind == "ul":
            lines.append(f"- {text}")
        elif kind == "ol":
            lines.append(f"1. {text}")
        else:  # paragraph
            lines.append(f"\\{text}" if _NEEDS_ESCAPE.match(text) else text)
        i += 1
    return lines


# ---------------------------------------------------------------------------
# Parse (Markdown → Book)
# ---------------------------------------------------------------------------

def _parse_items(md: str) -> list[tuple[int, str, str]]:
    """Flat list of (page_no, kind, text) in source order."""
    lines = md.split("\n")
    items: list[tuple[int, str, str]] = []
    cur_page = 0
    i, n = 0, len(lines)
    while i < n:
        text = lines[i].strip()
        if not text:
            i += 1
            continue
        m = _PAGE_RE.match(text)
        if m:
            cur_page = int(m.group(1))
            i += 1
            continue
        if text in (":::verse", ":::quran"):
            kind = text[3:]
            i += 1
            while i < n and lines[i].strip() != ":::":
                inner = lines[i].strip()
                if inner:
                    items.append((cur_page, kind, inner))
                i += 1
            i += 1  # skip closing fence
            continue
        m = _SCAN_RE.match(text)
        if m:
            items.append((cur_page, "img", m.group(1).strip()))
            i += 1
            continue
        if text.startswith("\\"):
            items.append((cur_page, "p", text[1:].strip()))
        elif text.startswith("### "):
            items.append((cur_page, "h3", text[4:].strip()))
        elif text.startswith("## "):
            items.append((cur_page, "h2", text[3:].strip()))
        elif text.startswith("# "):
            items.append((cur_page, "h1", text[2:].strip()))
        elif text.startswith("- "):
            items.append((cur_page, "ul", text[2:].strip()))
        elif _OL_RE.match(text):
            items.append((cur_page, "ol", _OL_RE.match(text).group(1).strip()))  # type: ignore[union-attr]
        else:
            items.append((cur_page, "p", text))
        i += 1
    return items


def markdown_to_book(md: str, *, title: str, author: str, language: str,
                     split_every: int) -> Book:
    items = _parse_items(md)

    # Chapter break level = the shallowest heading tier present; deeper tiers
    # become in-body headings. Mirrors the heading-count≥2 vs split_every rule.
    present = [k for _, k, _ in items if k in _HEAD_LEVEL]
    break_kind = min(present, key=lambda k: _HEAD_LEVEL[k]) if present else None
    heading_count = sum(1 for _, k, _ in items if k == break_kind) if break_kind else 0
    use_headings = heading_count >= 2

    # Group items by source page (markers are emitted in order).
    pages: list[tuple[int, list[Element]]] = []
    for page_no, kind, txt in items:
        if not pages or pages[-1][0] != page_no:
            pages.append((page_no, []))
        pages[-1][1].append((kind, txt))

    chapters: list[Chapter] = []
    current = Chapter(title="")
    pages_in_chapter = 0

    def flush() -> None:
        nonlocal current, pages_in_chapter
        if current.elements:
            chapters.append(current)
        current = Chapter(title="")
        pages_in_chapter = 0

    for page_no, els in pages:
        for kind, txt in els:
            if kind == "img":
                current.elements.append(PageImage(page_no, txt))
            elif kind in _HEAD_LEVEL and use_headings and kind == break_kind:
                # Two-line headings arrive as consecutive break-level headings;
                # merge them into one chapter title instead of an empty chapter.
                # Only merge into a *break-level* heading — a deeper in-body
                # heading must not swallow the chapter heading that follows it.
                only_heading_so_far = (
                    len(current.elements) == 1
                    and isinstance(current.elements[0], Paragraph)
                    and current.elements[0].kind == break_kind
                )
                if only_heading_so_far:
                    first = current.elements[0]
                    assert isinstance(first, Paragraph)
                    merged = f"{first.text} {txt}".strip()
                    current.elements[0] = Paragraph(merged, first.kind)
                    current.title = clean.clean_heading(merged) or current.title
                else:
                    flush()
                    current.title = clean.clean_heading(txt) or txt
                    current.elements.append(Paragraph(txt, kind))
            else:
                current.elements.append(Paragraph(txt, kind))
        pages_in_chapter += 1
        if not use_headings and pages_in_chapter >= max(1, split_every):
            flush()
    flush()

    if not chapters:
        chapters = [Chapter(title="", elements=[Paragraph("(لم يُتعرف على نص)", "p")])]
    return Book(title=title, author=author, language=language, chapters=chapters)
