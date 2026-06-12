"""Reflowable RTL EPUB builder for OCR'd / extracted Arabic text."""

from __future__ import annotations

import io
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

from ..book import Book, Chapter, PageImage, Paragraph
from .opf import ManifestItem, build_ncx, build_nav, build_opf
from .templates import FONT_FACE_CSS, REFLOW_CSS, xhtml_page
from .zipwriter import EpubContainer

MAX_EMBED_HEIGHT = 1024
JPEG_QUALITY = 70


def _chapter_xhtml(chapter: Chapter, work_root: Path, image_names: dict[int, str]) -> str:
    parts: list[str] = []
    for el in chapter.elements:
        if isinstance(el, Paragraph):
            if el.kind == "h2":
                parts.append(f"    <h2>{escape(el.text)}</h2>")
            elif el.kind in ("verse", "quran"):
                parts.append(f'    <p class="{el.kind}">{escape(el.text)}</p>')
            else:
                parts.append(f"    <p>{escape(el.text)}</p>")
        elif isinstance(el, PageImage):
            name = image_names[el.page_no]
            parts.append(
                f'    <figure class="scan"><img src="../{name}" alt="صفحة {el.page_no + 1}"/>'
                f"<figcaption>صفحة {el.page_no + 1}</figcaption></figure>"
            )
    return "\n".join(parts)


def _encode_scan(src: Path) -> bytes:
    with Image.open(src) as img:
        img = img.convert("L")
        if img.height > MAX_EMBED_HEIGHT:
            factor = MAX_EMBED_HEIGHT / img.height
            img = img.resize((max(1, int(img.width * factor)), MAX_EMBED_HEIGHT), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=JPEG_QUALITY, optimize=True)
        return buf.getvalue()


def build_reflow_epub(
    book: Book,
    out_path: Path,
    work_root: Path,
    font_files: list[Path] | None = None,
) -> Path:
    book_id = f"urn:uuid:{uuid.uuid4()}"
    items: list[ManifestItem] = [
        ManifestItem("nav", "nav.xhtml", "application/xhtml+xml", "nav"),
        ManifestItem("ncx", "toc.ncx", "application/x-dtbncx+xml"),
        ManifestItem("css", "styles/style.css", "text/css"),
    ]
    spine_ids: list[str] = []
    toc: list[tuple[str, str]] = []

    css = REFLOW_CSS
    font_files = font_files or []

    with EpubContainer(out_path) as epub:
        for font in font_files:
            family = "Amiri" if "amiri" in font.name.lower() else "Scheherazade New"
            css = FONT_FACE_CSS.format(family=family, filename=font.name) + css
            items.append(ManifestItem(
                f"font-{font.stem.lower()}", f"fonts/{font.name}",
                "application/font-sfnt",
            ))
            epub.add_file(f"OEBPS/fonts/{font.name}", font)
        epub.add("OEBPS/styles/style.css", css)

        # Collect and embed all scan images referenced by the book. The scan
        # of the book's first page (the cover, when kept as an image) is
        # declared as the EPUB cover so readers show a thumbnail.
        image_names: dict[int, str] = {}
        cover_id: str | None = None
        first_image_page = min(
            (el.page_no for ch in book.chapters for el in ch.elements
             if isinstance(el, PageImage)), default=None,
        )
        for chapter in book.chapters:
            for el in chapter.elements:
                if isinstance(el, PageImage) and el.page_no not in image_names:
                    src = work_root / el.image_path
                    name = f"images/scan_{el.page_no + 1:04d}.jpg"
                    item_id = f"scan{el.page_no + 1:04d}"
                    is_cover = el.page_no == first_image_page and el.page_no <= 1
                    if is_cover:
                        cover_id = item_id
                    epub.add(f"OEBPS/{name}", _encode_scan(src))
                    items.append(ManifestItem(item_id, name, "image/jpeg",
                                              "cover-image" if is_cover else ""))
                    image_names[el.page_no] = name

        for i, chapter in enumerate(book.chapters):
            name = f"text/chap_{i + 1:03d}.xhtml"
            body = _chapter_xhtml(chapter, work_root, image_names)
            heading = f"    <h2>{escape(chapter.title)}</h2>\n" if chapter.title else ""
            if not any(isinstance(e, Paragraph) and e.kind == "h2" for e in chapter.elements[:1]):
                body = heading + body
            epub.add(f"OEBPS/{name}", xhtml_page(chapter.title or book.title, body,
                                                 book.language, css_href="../styles/style.css"))
            chap_id = f"c{i + 1:03d}"
            items.append(ManifestItem(chap_id, name, "application/xhtml+xml"))
            spine_ids.append(chap_id)
            toc.append((chapter.title or f"فصل {i + 1}", name))

        epub.add("OEBPS/nav.xhtml", build_nav(book.title, book.language, toc))
        epub.add("OEBPS/toc.ncx", build_ncx(book.title, book_id, toc))
        epub.add("OEBPS/content.opf",
                 build_opf(book.title, book.author, book.language, items, spine_ids,
                           book_id=book_id, cover_id=cover_id))
    return out_path
