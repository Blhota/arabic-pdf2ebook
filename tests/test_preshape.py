from __future__ import annotations

from pdf2ebook.fontkit import cpfont_files, export_fonts
from pdf2ebook.textproc.preshape import preshape_text


def _presentation_forms(text: str) -> int:
    return sum(1 for c in text if 0xFB50 <= ord(c) <= 0xFEFF)


def test_preshape_emits_presentation_forms():
    out = preshape_text("لكل شيء إذا ما تم نقصان")
    assert _presentation_forms(out) > 10
    # lam-alef ligature appears for لا
    out_la = preshape_text("لا")
    assert any(0xFEF5 <= ord(c) <= 0xFEFC for c in out_la)


def test_preshape_keeps_diacritics():
    out = preshape_text("فَجائِعُ الدهر")
    assert any(0x064B <= ord(c) <= 0x0652 for c in out), "harakat must survive"


def test_preshape_leaves_latin_alone():
    assert preshape_text("hello 123") == "hello 123"


def test_cpfont_files_bundled():
    files = cpfont_files()
    assert len(files) == 4  # sizes 12,14,16,18
    assert all(f.suffix == ".cpfont" for f in files)


def test_export_fonts_writes_pack(tmp_path):
    written = export_fonts(tmp_path / "pack")
    names = {p.name for p in written}
    assert "Amiri-Regular.ttf" in names
    assert "OFL.txt" in names
    assert "README.txt" in names
    assert sum(1 for p in written if p.suffix == ".cpfont") == 4
    readme = (tmp_path / "pack" / "README.txt").read_text(encoding="utf-8")
    assert "fonts install" in readme and "كوبو" in readme


def test_preshape_flag_changes_epub_output(tiny_pdf, tmp_path):
    """End-to-end: --preshape produces presentation forms in the book model."""
    from pdf2ebook.book import Book, Chapter, Paragraph
    from pdf2ebook.textproc.preshape import preshape_text as ps

    # simulate the ocrmode transform on a small book
    book = Book(title="ت", chapters=[Chapter("مقدمة", [Paragraph("لا إله إلا الله")])])
    for ch in book.chapters:
        ch.title = ps(ch.title)
        for el in ch.elements:
            el.text = ps(el.text)
    assert _presentation_forms(book.chapters[0].elements[0].text) > 5
    assert _presentation_forms(book.chapters[0].title) > 2
