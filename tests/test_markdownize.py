from __future__ import annotations

import xml.dom.minidom
import zipfile

from pdf2ebook.book import PageImage, Paragraph
from pdf2ebook.epub.reflow import build_reflow_epub
from pdf2ebook.textproc.markdownize import (
    emit_elements,
    emit_page_break,
    emit_scan,
    markdown_to_book,
)


def _md(*pages: list) -> str:
    """Build a markdown doc from pages, each a (page_no, elements) tuple."""
    lines: list[str] = []
    for page_no, elements in pages:
        lines.append(emit_page_break(page_no))
        lines.extend(emit_elements(elements))
    return "\n".join(lines)


def test_verse_quran_roundtrip_is_exact():
    elements = [
        ("verse", "شطر أول  شطر ثان"),          # hemistich double-space preserved
        ("verse", "بيت ثان هنا  وتكملته"),
        ("quran", "﴿ ذلك الكتاب لا ريب فيه ﴾"),  # ornate brackets preserved
        ("p", "نص عادي بعد الآيات."),
    ]
    md = _md((0, elements))
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    out = [(p.kind, p.text) for ch in book.chapters for p in ch.elements
           if isinstance(p, Paragraph)]
    assert out == elements


def test_paragraph_starting_with_markdown_char_stays_paragraph():
    # Real Arabic text that happens to start with '#'/'-' must survive the trip.
    elements = [("p", "# ليست عنوانا بل فقرة"), ("p", "- ولا قائمة هنا"), ("p", "1. ولا ترقيم")]
    md = _md((0, elements))
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    out = [(p.kind, p.text) for ch in book.chapters for p in ch.elements
           if isinstance(p, Paragraph)]
    assert out == elements


def test_headings_split_into_chapters():
    md = _md(
        (0, [("h2", "الفصل الأول"), ("p", "نص الفصل الأول.")]),
        (1, [("h2", "الفصل الثاني"), ("p", "نص الفصل الثاني.")]),
    )
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    assert len(book.chapters) == 2
    assert book.chapters[0].title == "الفصل الأول"
    assert book.chapters[1].title == "الفصل الثاني"


def test_split_every_fallback_without_headings():
    pages = [(i, [("p", f"نص الصفحة رقم {i}.")]) for i in range(4)]
    md = _md(*pages)
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=2)
    assert len(book.chapters) == 2  # 4 pages / 2 per chapter


def test_deeper_heading_stays_in_body():
    # Document uses ## for chapters; ### is a sub-heading inside the chapter.
    md = _md(
        (0, [("h2", "الباب الأول"), ("h3", "مبحث"), ("p", "نص.")]),
        (1, [("h2", "الباب الثاني"), ("p", "نص آخر.")]),
    )
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    assert len(book.chapters) == 2
    first_kinds = [p.kind for p in book.chapters[0].elements if isinstance(p, Paragraph)]
    assert "h3" in first_kinds  # the sub-heading did not open a new chapter


def test_break_heading_not_merged_into_deeper_heading():
    # A deeper (h3) heading appears before the first chapter (h2) heading.
    # The h2 must start its own chapter, not get merged into the h3 title.
    md = _md(
        (0, [("h3", "تصدير"), ("h2", "الفصل الأول"), ("p", "نص.")]),
        (1, [("h2", "الفصل الثاني"), ("p", "نص آخر.")]),
    )
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    titles = [ch.title for ch in book.chapters]
    assert "الفصل الأول" in titles
    assert "الفصل الثاني" in titles
    assert not any("تصدير" in t and "الفصل" in t for t in titles)


def test_scan_image_maps_to_pageimage():
    lines = [emit_page_break(2), emit_scan("scans/page_0003.png")]
    md = "\n".join(lines)
    book = markdown_to_book(md, title="t", author="", language="ar", split_every=10)
    imgs = [el for ch in book.chapters for el in ch.elements if isinstance(el, PageImage)]
    assert len(imgs) == 1
    assert imgs[0].page_no == 2
    assert imgs[0].image_path == "scans/page_0003.png"


def test_full_chain_to_epub(tmp_path):
    scan = tmp_path / "scans" / "page_0002.png"
    scan.parent.mkdir()
    from PIL import Image
    Image.new("L", (400, 600), 200).save(scan)

    md = _md(
        (0, [("h1", "الباب الأول"), ("p", "فقرة افتتاحية."),
             ("ul", "أولا"), ("ul", "ثانيا"), ("h3", "مبحث"), ("p", "ختام.")]),
    )
    # add an image page after the text page
    md += "\n" + emit_page_break(1) + "\n" + emit_scan("scans/page_0002.png")
    book = markdown_to_book(md, title="كتاب", author="", language="ar", split_every=10)
    out = tmp_path / "book.epub"
    build_reflow_epub(book, out, tmp_path, font_files=[])

    zf = zipfile.ZipFile(out)
    assert zf.read("mimetype") == b"application/epub+zip"
    chap = zf.read("OEBPS/text/chap_001.xhtml").decode("utf-8")
    assert "<h1>" in chap
    assert "<ul>" in chap and chap.count("<li>") == 2
    assert "<h3>" in chap
    assert "figure" in chap  # the embedded scan
    xml.dom.minidom.parseString(chap)  # well-formed XHTML
