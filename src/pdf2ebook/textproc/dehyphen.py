"""Join wrapped lines into one paragraph, de-hyphenating Latin word breaks.

Arabic does not hyphenate across lines, so wrapped Arabic lines just get a
space. But mixed scholarly books contain Latin terms broken as "exam-\nple";
those are rejoined without the hyphen. The check is deliberately narrow (an
ASCII letter before the hyphen, a lowercase ASCII letter after) so Arabic and
genuine dashes are never touched.
"""

from __future__ import annotations

_HYPHENS = "-‐‑"


def join_wrapped(lines: list[str]) -> str:
    parts = [ln.strip() for ln in lines if ln.strip()]
    if not parts:
        return ""
    out = parts[0]
    for nxt in parts[1:]:
        prev = out.rstrip()
        latin_break = (
            len(prev) >= 2
            and prev[-1] in _HYPHENS
            and prev[-2].isascii() and prev[-2].isalpha()
            and nxt[:1].isascii() and nxt[:1].isalpha() and nxt[:1].islower()
        )
        out = prev[:-1] + nxt if latin_break else prev + " " + nxt
    return out.strip()
