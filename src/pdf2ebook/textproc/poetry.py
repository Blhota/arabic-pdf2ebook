"""Classical Arabic poetry and Quranic quote handling.

Poetry: classical verse is printed one بيت per line, hemistichs side by side.
Merging those lines into prose paragraphs destroys the poem, so we detect
poetry blocks and keep every verse on its own line. Signals per line: no
terminal punctuation, moderate word count, and — the strong one — a shared
rhyme letter (الرويّ) across neighbouring lines.

Quran: quotes are set in ornate brackets ﴿…﴾ which OCR often misreads as
«…». When a bracketed quote sits next to a citation cue (قال تعالى, قرآن
كريم, سورة…), we restore the ornate brackets and mark the paragraph so the
EPUB styles it distinctly.
"""

from __future__ import annotations

import re

from ..ocr.base import OcrLine, OcrPage

_DIACRITICS_RE = re.compile(r"[ً-ْٰٕٔ]")
_NON_LETTER_END_RE = re.compile(r"[^ء-ي]+$")
TERMINAL_PUNCT = ".؟!:»۔"

MIN_BLOCK = 4  # minimum consecutive verse-like lines to call it a poem


def _rhyme_letter(text: str) -> str:
    """Final TWO Arabic letters of the line (the rhyme key).

    A single shared final letter is far too weak — Arabic prose lines end in
    ن/م/ة/ا constantly. Two letters (e.g. 'ان' in أحزان/سلوان/بلدان) almost
    never repeat across consecutive prose lines by accident.
    """
    text = _DIACRITICS_RE.sub("", text.strip())
    text = _NON_LETTER_END_RE.sub("", text)
    if len(text) < 2:
        return ""
    return text[-2:]


def _verse_candidate(line: OcrLine) -> bool:
    text = line.text.strip()
    if not text:
        return False
    words = text.split()
    if not (3 <= len(words) <= 16):
        return False
    return text[-1] not in TERMINAL_PUNCT


def detect_verse_lines(page: OcrPage) -> set[int]:
    """Indices (into the page's non-empty lines) that belong to poetry blocks."""
    lines = [ln for ln in page.lines if ln.text.strip()]
    n = len(lines)
    verse: set[int] = set()
    i = 0
    while i < n:
        if not _verse_candidate(lines[i]):
            i += 1
            continue
        j = i
        while j < n and _verse_candidate(lines[j]):
            j += 1
        block = list(range(i, j))
        if len(block) >= MIN_BLOCK:
            rhymes = [_rhyme_letter(lines[k].text) for k in block]
            non_empty = [r for r in rhymes if r]
            if non_empty:
                top = max(set(non_empty), key=non_empty.count)
                # Shared two-letter rhyme across most of the block = poem.
                if non_empty.count(top) >= max(MIN_BLOCK, round(0.7 * len(block))):
                    verse.update(block)
        i = j
    return verse


def split_hemistichs(line: OcrLine) -> tuple[str, str] | None:
    """Split a verse on the central column gap when the OCR boxes preserved it."""
    words = sorted((w for w in line.words if w.text.strip()), key=lambda w: w.bbox[0])
    if len(words) < 4:
        return None
    line_left = words[0].bbox[0]
    line_right = words[-1].bbox[0] + words[-1].bbox[2]
    width = max(1, line_right - line_left)
    best_gap, best_idx = 0, -1
    for i in range(len(words) - 1):
        gap = words[i + 1].bbox[0] - (words[i].bbox[0] + words[i].bbox[2])
        if gap > best_gap:
            best_gap, best_idx = gap, i
    if best_gap < 0.12 * width:
        return None
    gap_center = words[best_idx].bbox[0] + words[best_idx].bbox[2] + best_gap / 2
    rel = (gap_center - line_left) / width
    if not 0.3 <= rel <= 0.7:
        return None
    # Words are in visual left-to-right order; Arabic reads right to left,
    # so the right-hand group is the first hemistich.
    left = " ".join(w.text for w in words[: best_idx + 1])
    right = " ".join(w.text for w in words[best_idx + 1:])
    return right, left


HEMISTICH_SEP = "  "  # two em-spaces between hemistichs


def verse_text(line: OcrLine) -> str:
    parts = split_hemistichs(line)
    if parts:
        return f"{parts[0]}{HEMISTICH_SEP}{parts[1]}"
    # OCR often misreads the column divider as | or _ — show a clean gap.
    return re.sub(r"\s*[|_]+\s*", HEMISTICH_SEP, line.text.strip())


# ---------------------------------------------------------------------------
# Quranic quotes
# ---------------------------------------------------------------------------

QURAN_CUE_RE = re.compile(r"قال\s+(الله\s+)?تعالى|قوله\s+تعالى|قرآن\s+كريم|سورة\s+\S+|عز\s+وجل")
QURAN_ATTRIBUTION_RE = re.compile(r"^\s*(قرآن\s+كريم|سورة\s+\S+(\s+آية\s+\S+)?)\s*$")
_BRACKETED_RE = re.compile(r"[«﴿]([^«»﴿﴾]{8,400})[»﴾]")


def mark_quran(text: str, has_cue_nearby: bool) -> tuple[str, bool]:
    """Restore ornate brackets on Quranic quotes; report if the paragraph is
    dominated by the quote (so it can be styled as a Quran block)."""
    if not has_cue_nearby:
        return text, False
    matches = list(_BRACKETED_RE.finditer(text))
    if not matches:
        return text, False
    quoted_len = sum(m.end() - m.start() for m in matches)
    out = _BRACKETED_RE.sub(lambda m: f"﴿{m.group(1).strip(' *')}﴾", text)
    return out, quoted_len >= 0.6 * len(text)


def attributed_quran(text: str) -> str:
    """Clean a paragraph that an attribution line explicitly marks as Quran.

    OCR often loses one or both ornate brackets (or turns them into « » or *);
    since the book itself labels the quote, restore the brackets around it.
    """
    body = text.strip().strip("«»*").strip()
    body = re.sub(r"[«»]", " ", body)
    body = re.sub(r"\s+", " ", body).strip()
    return f"﴿{body}﴾"
