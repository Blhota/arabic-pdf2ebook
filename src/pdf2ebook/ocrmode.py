"""OCR / auto mode: scanned pages → recognized text → reflowable RTL EPUB.

Per-page decision tree (auto mode):
    1. real PDF text layer (> TEXT_LAYER_MIN_CHARS, healthy) → use it directly
    2. page looks like a photo/map                  → keep as cleaned image
    3. OCR; low-confidence pages get a rescue pass  → text
    4. still below --min-conf                       → keep as cleaned image

Junk removal happens at the *line* level before paragraphs are built, so an
OCR-mangled watermark can never be merged into a real paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from .book import Book, Chapter, PageImage, Paragraph
from .config import PipelineOptions, parse_page_range
from .epub.reflow import build_reflow_epub
from .ocr.base import OcrPage
from .ocr.registry import get_backend
from .pdfio import PdfRasterizer
from .pipeline import ConversionResult, Progress, default_title, default_work_dir, extract_pages
from .preprocess import ops
from .preprocess.pipeline import detect_image_page, preprocess_for_image, preprocess_for_ocr
from .textproc import clean
from .textproc.markdownize import emit_elements, emit_page_break, emit_scan, markdown_to_book
from .textproc.paragraphs import merge_page_boundary
from .textproc.structure import structure_page
from .workdir import WorkDir

TEXT_LAYER_MIN_CHARS = 200
MIN_WORDS_PER_PAGE = 15
SCAN_MAX_HEIGHT = 1400

DropLine = Callable[[str, bool], bool]  # (line_text, is_page_edge) -> drop?


@dataclass
class PageData:
    index: int
    kind: str  # "text" | "ocr" | "image"
    payload: object = None  # OcrPage | None (text + ocr pages both carry an OcrPage)
    elements: list[tuple[str, str]] = field(default_factory=list)  # (kind, text)
    image_rel: str | None = None
    mean_conf: float = 100.0

    def line_texts(self) -> list[str]:
        if self.kind in ("ocr", "text") and self.payload is not None:
            return [ln.text for ln in self.payload.lines if ln.text.strip()]
        return []


# ---------------------------------------------------------------------------
# Stages
# ---------------------------------------------------------------------------

def preprocess_ocr_pages(work: WorkDir, raw_paths: list[Path], force: bool = False,
                         progress: Progress | None = None) -> dict[str, Path]:
    settings = {"v": 1}
    if force:
        work.invalidate("pre-ocr")
    work.begin_stage("pre-ocr", settings)
    out: dict[str, Path] = {}
    for n, src in enumerate(raw_paths):
        dest = work.root / "pre-ocr" / src.name
        if not dest.exists():
            with Image.open(src) as img:
                preprocess_for_ocr(img).save(dest, format="PNG")
        out[src.name] = dest
        if progress:
            progress("preprocess", n + 1, len(raw_paths))
    return out


def _alternate_ocr_image(raw_path: Path) -> Image.Image:
    """Different binarization recipe for the rescue pass."""
    with Image.open(raw_path) as img:
        gray = ops.from_pil(img)
    gray = ops.deskew(gray)
    gray = ops.clahe(gray)
    binary = ops.otsu(gray)
    binary = ops.autocrop(binary)
    binary = ops.upscale_if_small(binary)
    return ops.to_pil(binary)


def _make_scan_image(work: WorkDir, raw_path: Path, index: int) -> str:
    """Cleaned grayscale rendition of a page kept as an image; returns rel path."""
    scans = work.stage_dir("scans")
    dest = scans / WorkDir.page_name(index, "png")
    if not dest.exists():
        with Image.open(raw_path) as img:
            cleaned = preprocess_for_image(img, 0, 0, style="gray")
            if cleaned.height > SCAN_MAX_HEIGHT:
                factor = SCAN_MAX_HEIGHT / cleaned.height
                cleaned = cleaned.resize(
                    (max(1, int(cleaned.width * factor)), SCAN_MAX_HEIGHT), Image.LANCZOS)
            cleaned.save(dest, format="PNG")
    return str(dest.relative_to(work.root))


# ---------------------------------------------------------------------------
# Chapter weighting / giant-chapter splitting
# ---------------------------------------------------------------------------

def _modal_body_size(pages: dict[int, OcrPage]) -> float:
    """Most common line font size across text-layer pages (anchors heading tiers)."""
    from collections import Counter

    counts: Counter[int] = Counter()
    for page in pages.values():
        for ln in page.lines:
            if ln.size > 0 and ln.text.strip():
                counts[round(ln.size)] += 1
    return float(counts.most_common(1)[0][0]) if counts else 0.0


def _element_weight(el: Paragraph | PageImage) -> int:
    """Approximate EPUB byte cost: an embedded scan ≈ 150k chars of text."""
    return len(el.text) if isinstance(el, Paragraph) else 150_000


# Readers struggle with giant chapter files (spec guidance ~300 KB/XHTML);
# huge undetected-heading books can produce multi-megabyte chapters.
MAX_CHAPTER_WEIGHT = 400_000
TARGET_CHAPTER_WEIGHT = 250_000


def _split_giant_chapters(chapters: list[Chapter]) -> list[Chapter]:
    from .pipeline import _volume_chunks

    out: list[Chapter] = []
    for chapter in chapters:
        weights = [_element_weight(el) for el in chapter.elements]
        total = sum(weights)
        if total <= MAX_CHAPTER_WEIGHT or len(chapter.elements) <= 3:
            out.append(chapter)
            continue
        parts = max(2, round(total / TARGET_CHAPTER_WEIGHT))
        for k, els in enumerate(_volume_chunks(chapter.elements, parts, weights)):
            part_title = chapter.title if k == 0 else f"{chapter.title} ({k + 1})"
            out.append(Chapter(part_title, els))
    return out


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

def run_text_mode(
    pdf_path: Path,
    out_path: Path,
    opts: PipelineOptions,
    progress: Progress | None = None,
) -> ConversionResult:
    result = ConversionResult()
    work = WorkDir(opts.work_dir or default_work_dir(pdf_path), pdf_path)
    extra_patterns = clean.compile_extra_patterns(opts.ocr.strip_patterns)

    with PdfRasterizer(pdf_path) as pdf:
        indices = parse_page_range(opts.pages, pdf.page_count)
        result.pages_total = len(indices)
        if not opts.meta.author:
            opts.meta.author = pdf.metadata().get("author", "")
        force_extract = opts.force in ("extract", "all")
        raw_paths = extract_pages(pdf, work, indices, opts.dpi, force_extract, progress)
        raw_by_index = dict(zip(indices, raw_paths))

        # 1. Which pages can use the PDF's own text layer? (auto mode only)
        #    Kept pages are extracted *with geometry* (an OcrPage with per-line
        #    font sizes) so they get the same structuring as OCR pages.
        direct_pages: dict[int, OcrPage] = {}
        if opts.mode == "auto" and opts.text_layer != "never":
            samples: dict[int, str] = {}
            for idx in indices:
                stripped = pdf.extract_text(idx).strip()
                if len(stripped) >= TEXT_LAYER_MIN_CHARS:
                    samples[idx] = stripped
            use_layer = bool(samples)
            # Quality gate: many scanned books embed a *broken* text layer
            # (lam-alef ligatures lose the alef, hamza forms scramble).
            # When the sampled text looks corrupted, ignore the whole layer
            # and OCR instead — unless the user forces --text-layer always.
            if use_layer and opts.text_layer == "auto":
                sample = "\n".join(list(samples.values())[:10])
                if clean.looks_corrupted_arabic(sample):
                    use_layer = False
            if use_layer:
                for idx in samples:
                    page = pdf.extract_text_page(idx)
                    if page and page.lines:
                        direct_pages[idx] = page

    # Body font size (the modal line size across text-layer pages) anchors the
    # heading tiers; OCR pages have no font size and fall back to line height.
    body_size = _modal_body_size(direct_pages)

    # 2. Recognition pass: text layer / OCR / image per page.
    ocr_indices = [i for i in indices if i not in direct_pages]
    force_pre = opts.force in ("preprocess", "all") or force_extract
    pre_paths = preprocess_ocr_pages(
        work, [raw_by_index[i] for i in ocr_indices], force_pre, progress
    ) if ocr_indices else {}

    backend = None
    pages_data: list[PageData] = []
    ocr_stage = f"ocr-{opts.ocr.engine}"
    ocr_settings = {"engine": opts.ocr.engine, "lang": opts.ocr.lang,
                    "psm": opts.ocr.psm, "rescue": opts.ocr.rescue, "v": 1}
    if opts.force in ("ocr", "all"):
        work.invalidate(ocr_stage)
    work.begin_stage(ocr_stage, ocr_settings)

    rescue_threshold = opts.ocr.min_conf + 15

    for n, idx in enumerate(indices):
        if idx in direct_pages:
            pages_data.append(PageData(index=idx, kind="text", payload=direct_pages[idx]))
            result.pages_direct_text += 1
            continue

        raw_path = raw_by_index[idx]
        cache = work.page_path(ocr_stage, idx, "json")

        if cache.exists():
            ocr_page = OcrPage.from_json(cache.read_text(encoding="utf-8"))
        else:
            with Image.open(raw_path) as raw_img:
                is_image_page = detect_image_page(raw_img)
            if is_image_page:
                ocr_page = OcrPage(page_no=idx, size=(0, 0), lines=[])
            else:
                if backend is None:
                    backend = get_backend(opts.ocr.engine, lang=opts.ocr.lang, psm=opts.ocr.psm)
                ocr_page = backend.recognize(pre_paths[raw_path.name])
                ocr_page.page_no = idx
                if opts.ocr.rescue and ocr_page.mean_conf < rescue_threshold:
                    alt_path = work.stage_dir("pre-ocr-alt") / raw_path.name
                    if not alt_path.exists():
                        _alternate_ocr_image(raw_path).save(alt_path, format="PNG")
                    retry = backend.recognize(alt_path)
                    retry.page_no = idx
                    if retry.mean_conf > ocr_page.mean_conf:
                        ocr_page = retry
            cache.write_text(ocr_page.to_json(), encoding="utf-8")

        good = (ocr_page.mean_conf >= opts.ocr.min_conf
                and ocr_page.word_count >= MIN_WORDS_PER_PAGE)
        if good:
            # Foreign-script pages (Latin bibliographies, dot-leader indexes)
            # OCR into glyph soup under an Arabic model — keep them as images.
            # Calibrated on real books: genuine Arabic pages score >= 0.74,
            # an OCR'd French bibliography scored 0.60.
            page_text = " ".join(ln.text for ln in ocr_page.lines)
            if clean.arabic_ratio(page_text) < 0.65:
                good = False
        if good:
            pages_data.append(PageData(index=idx, kind="ocr", payload=ocr_page,
                                       mean_conf=ocr_page.mean_conf))
            result.pages_ocr += 1
            result.mean_confidences.append(ocr_page.mean_conf)
        else:
            data = PageData(index=idx, kind="image", mean_conf=ocr_page.mean_conf)
            data.image_rel = _make_scan_image(work, raw_path, idx)
            pages_data.append(data)
            result.pages_image_fallback += 1
        if progress:
            progress("ocr", n + 1, len(indices))

    # 3. Detect repeated headers/footers, then build elements with the
    #    line-level junk filter (watermarks never reach paragraph building).
    repeated = clean.find_repeated_lines([p.line_texts() for p in pages_data
                                          if p.kind != "image"])
    result.stripped_lines = repeated

    def drop_line(text: str, edge: bool) -> bool:
        if clean.is_watermark(text, extra_patterns):
            return True
        if clean.is_page_number(text):
            return True
        if clean.is_junk_line(text, edge=edge):
            return True
        return bool(repeated) and clean.matches_repeated(text, repeated)

    for data in pages_data:
        if data.kind in ("ocr", "text"):
            data.elements = structure_page(data.payload, opts.ocr.keep_diacritics,
                                           drop_line, body_size)

    # 4. Merge paragraphs across page boundaries.
    for prev, cur in zip(pages_data, pages_data[1:]):
        if prev.kind == "image" or cur.kind == "image":
            continue
        if not prev.elements or not cur.elements:
            continue
        if prev.elements[-1][0] != "p" or cur.elements[0][0] != "p":
            continue
        merged_prev, merged_cur = merge_page_boundary(
            [prev.elements[-1][1]], [cur.elements[0][1]]
        )
        if len(merged_cur) == 0:  # merge happened
            prev.elements[-1] = ("p", merged_prev[-1])
            cur.elements.pop(0)

    # 5. Serialize the structured pages to an in-memory Markdown document, then
    #    parse it back into the Book model (PDF → Markdown → EPUB). The Markdown
    #    is never written to disk unless --debug-markdown is set.
    md_lines: list[str] = []
    for data in pages_data:
        md_lines.append(emit_page_break(data.index))
        if data.kind == "image":
            if data.image_rel:
                md_lines.append(emit_scan(data.image_rel))
        else:
            md_lines.extend(emit_elements(data.elements))
    markdown = "\n".join(md_lines)
    if opts.debug_markdown:
        Path(opts.debug_markdown).write_text(markdown, encoding="utf-8")

    title = opts.meta.title or default_title(pdf_path)
    book = markdown_to_book(markdown, title=title, author=opts.meta.author,
                            language=opts.meta.language, split_every=opts.split_every)

    book.chapters = _split_giant_chapters(book.chapters)
    for i, chapter in enumerate(book.chapters):
        if not chapter.title:
            chapter.title = f"قسم {i + 1}"

    # Optional final transform: bake letter-joining into the text for simple
    # renderers (CrossPoint etc.). Must come after the Markdown round-trip
    # (preshape only touches final Arabic glyphs, never markup).
    if opts.preshape:
        from .textproc.preshape import preshape_text

        for chapter in book.chapters:
            chapter.title = preshape_text(chapter.title)
            for el in chapter.elements:
                if isinstance(el, Paragraph):
                    el.text = preshape_text(el.text)

    text_dir = work.stage_dir("text")
    book.save(text_dir / "book.json")

    # 6. Build EPUB volume(s).
    from .pipeline import _volume_chunks, _volume_path

    font_files = resolve_fonts(opts.font)
    # Weight chapters by content so multi-volume splits come out even.
    weights = [sum(_element_weight(el) for el in ch.elements) for ch in book.chapters]
    chunks = _volume_chunks(book.chapters, opts.split_volumes, weights)
    for vol, chunk in enumerate(chunks):
        vol_title = title if len(chunks) == 1 else f"{title} — {vol + 1}"
        vol_out = _volume_path(out_path, vol, len(chunks))
        vol_book = Book(title=vol_title, author=book.author, language=book.language,
                        chapters=chunk)
        build_reflow_epub(vol_book, vol_out, work.root, font_files)
        result.outputs.append(vol_out)
        if progress:
            progress("epub", vol + 1, len(chunks))

    if opts.clean:
        work.cleanup()
    return result


def resolve_fonts(choice: str) -> list[Path]:
    if choice == "none":
        return []
    fonts_dir = Path(__file__).parent / "fonts"
    mapping = {
        "amiri": ["Amiri-Regular.ttf"],
        "scheherazade": ["ScheherazadeNew-Regular.ttf"],
    }
    files = [fonts_dir / name for name in mapping.get(choice, [])]
    return [f for f in files if f.exists()]
