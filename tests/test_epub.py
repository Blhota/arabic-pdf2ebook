from __future__ import annotations

import xml.dom.minidom
import zipfile
from pathlib import Path

from PIL import Image

from pdf2ebook.book import Book, Chapter, PageImage, Paragraph
from pdf2ebook.epub.fixedlayout import build_image_epub
from pdf2ebook.epub.reflow import build_reflow_epub


def _make_pages(tmp_path: Path, n: int = 2) -> list[Path]:
    paths = []
    for i in range(n):
        p = tmp_path / f"page_{i + 1:04d}.png"
        Image.new("L", (400, 600), 240).save(p)
        paths.append(p)
    return paths


def _assert_valid_epub(path: Path) -> zipfile.ZipFile:
    zf = zipfile.ZipFile(path)
    infos = zf.infolist()
    assert infos[0].filename == "mimetype"
    assert infos[0].compress_type == zipfile.ZIP_STORED
    assert zf.read("mimetype") == b"application/epub+zip"
    opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert 'page-progression-direction="rtl"' in opf
    assert 'dir="rtl"' in opf
    assert "<dc:language>ar</dc:language>" in opf
    xml.dom.minidom.parseString(opf)
    xml.dom.minidom.parseString(zf.read("OEBPS/nav.xhtml"))
    xml.dom.minidom.parseString(zf.read("OEBPS/toc.ncx"))
    return zf


def test_image_epub_structure(tmp_path):
    pages = _make_pages(tmp_path)
    out = tmp_path / "book.epub"
    build_image_epub(pages, out, title="كتاب تجريبي", style="gray", layout="flow")
    zf = _assert_valid_epub(out)
    assert len([n for n in zf.namelist() if n.startswith("OEBPS/pages/")]) == 2
    page1 = zf.read("OEBPS/pages/page_0001.xhtml").decode("utf-8")
    assert 'dir="rtl"' in page1 and 'lang="ar"' in page1


def test_image_epub_fixed_layout(tmp_path):
    pages = _make_pages(tmp_path)
    out = tmp_path / "fixed.epub"
    build_image_epub(pages, out, title="ت", layout="fixed", viewport=(480, 800))
    zf = _assert_valid_epub(out)
    opf = zf.read("OEBPS/content.opf").decode("utf-8")
    assert "pre-paginated" in opf


def test_reflow_epub_with_scan_fallback(tmp_path):
    scan = tmp_path / "scans" / "page_0002.png"
    scan.parent.mkdir()
    Image.new("L", (400, 600), 200).save(scan)
    book = Book(
        title="محاكم التفتيش",
        chapters=[
            Chapter("الفصل الأول", [
                Paragraph("الفصل الأول", "h2"),
                Paragraph("نص الفقرة الأولى من الكتاب."),
                PageImage(1, "scans/page_0002.png"),
            ]),
            Chapter("الفصل الثاني", [Paragraph("نص الفصل الثاني.")]),
        ],
    )
    out = tmp_path / "reflow.epub"
    build_reflow_epub(book, out, tmp_path, font_files=[])
    zf = _assert_valid_epub(out)
    chap1 = zf.read("OEBPS/text/chap_001.xhtml").decode("utf-8")
    assert "نص الفقرة الأولى" in chap1
    assert "figure" in chap1  # embedded scan fallback
    assert any(n.startswith("OEBPS/images/scan_") for n in zf.namelist())
    # two chapters in spine and toc
    assert len([n for n in zf.namelist() if n.startswith("OEBPS/text/")]) == 2
