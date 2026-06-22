from __future__ import annotations

from pdf2ebook.ocr.base import OcrLine, OcrPage, OcrWord
from pdf2ebook.textproc.dehyphen import join_wrapped
from pdf2ebook.textproc.headings import heading_tiers
from pdf2ebook.textproc.lists import detect_list_items
from pdf2ebook.textproc.structure import structure_page


def _line(text: str, x: int, y: int, w: int, h: int = 14, size: float = 0.0) -> OcrLine:
    return OcrLine(words=[OcrWord(text, 100.0, (x, y, w, h))], bbox=(x, y, w, h), size=size)


def _no_drop(text: str, edge: bool) -> bool:
    return False


def test_font_size_heading_tiers():
    # Body size 12; sizes 24/18/14/12 → h1/h2/h3/none. Centered to pass the gate.
    page = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("عنوان كبير", 400, 10, 200, 30, size=24),
        _line("عنوان متوسط", 400, 60, 200, 24, size=18),
        _line("عنوان صغير", 400, 110, 200, 18, size=14),
        _line("سطر نص عادي", 400, 160, 200, 14, size=12),
    ])
    tiers = heading_tiers(page, body_size=12.0)
    assert tiers == {0: "h1", 1: "h2", 2: "h3"}


def test_ocr_height_fallback_heading():
    # No font size (OCR): a tall, centered line is a heading via height ratio.
    page = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("الباب الأول", 400, 10, 200, 45),   # ~2.6x median height
        _line("نص الفقرة العادية هنا", 100, 70, 800, 14),
        _line("سطر آخر من النص العادي", 100, 100, 800, 14),
    ])
    tiers = heading_tiers(page, body_size=0.0)
    assert 0 in tiers and tiers[0] in ("h1", "h2", "h3")
    assert 1 not in tiers and 2 not in tiers


def test_list_detection_bullets_and_numbers():
    bullets = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("• البند الأول", 100, 10, 400),
        _line("• البند الثاني", 100, 40, 400),
    ])
    items = detect_list_items(bullets)
    assert items == {0: ("ul", "البند الأول"), 1: ("ul", "البند الثاني")}

    numbered = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("١. أولا", 100, 10, 400),
        _line("٢. ثانيا", 100, 40, 400),
        _line("3) ثالثا", 100, 70, 400),
    ])
    items = detect_list_items(numbered)
    assert items[0] == ("ol", "أولا")
    assert items[2] == ("ol", "ثالثا")


def test_single_dash_line_is_not_a_list():
    page = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("- سطر وحيد يبدأ بشرطة وليس قائمة", 100, 10, 600),
        _line("نص عادي يتبعه.", 100, 40, 600),
    ])
    assert detect_list_items(page) == {}


def test_dehyphenation_latin_only():
    assert join_wrapped(["exam-", "ple done."]) == "example done."
    # Arabic wraps are space-joined, never de-hyphenated.
    assert join_wrapped(["السطر الأول", "والسطر الثاني"]) == "السطر الأول والسطر الثاني"


def test_structure_page_emits_list_and_heading():
    page = OcrPage(page_no=0, size=(1000, 1000), lines=[
        _line("الباب الأول", 400, 10, 200, 30, size=24),
        _line("هذه فقرة افتتاحية تحتوي على نص كافٍ للقراءة.", 100, 60, 800, 12, size=12),
        _line("• أولا", 100, 100, 400, 12, size=12),
        _line("• ثانيا", 100, 130, 400, 12, size=12),
    ])
    els = structure_page(page, keep_diacritics=True, drop_line=_no_drop, body_size=12.0)
    kinds = [k for k, _ in els]
    assert kinds[0] == "h1"
    assert "p" in kinds
    assert kinds.count("ul") == 2
