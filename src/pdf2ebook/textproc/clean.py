"""Arabic text cleanup: normalization, watermark/header/page-number removal.

Normalization is deliberately conservative — old orthography (hamza/alef
variants) is content, not noise. We only remove typographic artifacts.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

TATWEEL = "ـ"
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"

# Lines matching any of these are stripped wherever they appear.
SEED_WATERMARK_PATTERNS = [
    re.compile(r"https?://\S+", re.IGNORECASE),
    re.compile(r"www\.\S+", re.IGNORECASE),
    re.compile(r"kotob\s*\.?\s*has\s*\.?\s*it", re.IGNORECASE),
    re.compile(r"noor[\s-]*book", re.IGNORECASE),
]

PAGE_NUMBER_RE = re.compile(
    rf"^\s*[-–—(\[]?\s*[0-9{ARABIC_INDIC_DIGITS}]{{1,4}}\s*[-–—)\]]?\s*$"
)


def normalize_arabic(text: str, keep_diacritics: bool = True) -> str:
    """Fold presentation forms to base letters, strip tatweel, tidy whitespace."""
    # NFKC folds Arabic presentation forms (U+FB50..U+FEFF) into base letters.
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(TATWEEL, "")
    if not keep_diacritics:
        text = re.sub(r"[ً-ْٰ]", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


def _fuzzy_key(line: str) -> str:
    """Reduce a line to a comparison key tolerant of OCR noise."""
    line = normalize_arabic(line, keep_diacritics=False).lower()
    return re.sub(r"[\W_]+", "", line, flags=re.UNICODE)


def is_watermark(line: str, extra_patterns: list[re.Pattern] | None = None) -> bool:
    candidates = SEED_WATERMARK_PATTERNS + (extra_patterns or [])
    return any(p.search(line) for p in candidates)


def is_page_number(line: str) -> bool:
    return bool(PAGE_NUMBER_RE.match(line))


def find_repeated_lines(pages_lines: list[list[str]], min_ratio: float = 0.4,
                        fuzzy: float = 0.85) -> list[str]:
    """Detect running headers/footers/watermarks: short lines whose fuzzy key
    appears on more than `min_ratio` of pages (catches OCR-mangled URLs)."""
    if len(pages_lines) < 5:
        return []
    # Only consider first/last two lines of each page — headers and footers.
    candidates: dict[str, int] = {}
    representative: dict[str, str] = {}
    for lines in pages_lines:
        edges = lines[:2] + lines[-2:]
        seen_keys: set[str] = set()
        for line in edges:
            if len(line) > 60 or not line.strip():
                continue
            key = _fuzzy_key(line)
            if not key or len(key) < 4:
                continue
            # Fuzzy-merge with an existing key when nearly identical.
            merged = key
            for known in candidates:
                if abs(len(known) - len(key)) <= 4 and SequenceMatcher(None, known, key).ratio() >= fuzzy:
                    merged = known
                    break
            if merged in seen_keys:
                continue
            seen_keys.add(merged)
            candidates[merged] = candidates.get(merged, 0) + 1
            representative.setdefault(merged, line.strip())

    threshold = max(3, int(len(pages_lines) * min_ratio))
    repeated_keys = {k for k, count in candidates.items() if count >= threshold}
    return [representative[k] for k in repeated_keys]


def matches_repeated(line: str, repeated: list[str], fuzzy: float = 0.85) -> bool:
    key = _fuzzy_key(line)
    if not key:
        return False
    for rep in repeated:
        rep_key = _fuzzy_key(rep)
        if rep_key and SequenceMatcher(None, rep_key, key).ratio() >= fuzzy:
            return True
    return False


def compile_extra_patterns(patterns: list[str]) -> list[re.Pattern]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Signals of a broken embedded text layer (bad CMap / lossy OCR by the PDF
# producer). The classic symptom: the lam-alef ligature لا decomposes into a
# bare ل, so "لا شيء" turns into "ل شيء" and "الإسلامية" into "السإلمية".
_STANDALONE_LAM_RE = re.compile(r"(?:^|\s)ل(?:\s|$)")
_MISORDERED_HAMZA_RE = re.compile(r"[بتثجحخسشصضطظعغفقكمنهي][إأآ]")


def looks_corrupted_arabic(text: str, sample_chars: int = 4000) -> bool:
    sample = text[:sample_chars]
    words = sample.split()
    if len(words) < 40:
        return False
    standalone_lam = len(_STANDALONE_LAM_RE.findall(sample))
    misordered = len(_MISORDERED_HAMZA_RE.findall(sample))
    return (standalone_lam / len(words)) > 0.01 or (misordered / len(words)) > 0.02
