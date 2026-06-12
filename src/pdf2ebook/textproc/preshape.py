"""Pre-shaping: bake Arabic letter-joining into the text itself.

Simple e-reader renderers (CrossPoint on ESP32, some legacy devices) draw one
glyph per codepoint with no Arabic shaping engine, so normal Arabic shows as
disconnected letters (or boxes when glyphs are missing). Converting the text
to Arabic Presentation Forms (U+FB50-FEFF) makes the joining explicit in the
codepoints, so any renderer with those glyphs shows connected Arabic.

This is OPT-IN (--preshape): proper readers (Apple Books, Kobo, KOReader,
phone apps) shape Arabic themselves and must receive normal text.
"""

from __future__ import annotations

import arabic_reshaper

_RESHAPER: arabic_reshaper.ArabicReshaper | None = None


def _get_reshaper() -> arabic_reshaper.ArabicReshaper:
    global _RESHAPER
    if _RESHAPER is None:
        _RESHAPER = arabic_reshaper.ArabicReshaper({
            "delete_harakat": False,   # keep diacritics — content, not noise
            "delete_tatweel": True,
            "support_ligatures": True,  # lam-alef etc.
        })
    return _RESHAPER


def preshape_text(text: str) -> str:
    return _get_reshaper().reshape(text)
