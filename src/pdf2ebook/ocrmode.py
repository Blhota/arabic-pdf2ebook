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
from .textproc import clean, poetry
from .textproc.chapters import detect_heading_lines, looks_like_heading_text
from .textproc.paragraphs import TERMINAL_PUNCT, merge_page_boundary, page_paragraphs
from .workdir import WorkDir

TEXT_LAYER_MIN_CHARS = 200
MIN_WORDS_PER_PAGE = 15
SCAN_MAX_HEIGHT = 1400

DropLine = Callable[[str, bool], bool]  # (line_text, is_page_edge) -> drop?


@dataclass
class PageData:
    index: int
    kind: str  # "text" | "ocr" | "image"
    payload: object = None  # OcrPage | str | None
    elements: list[tuple[str, str]] = field(default_factory=list)  # (p|h2, text)
    image_rel: str | None = None
    mean_conf: float = 100.0

    def line_texts(self) -> list[str]:
        if self.kind == "ocr":
            return [ln.text for ln in self.payload.lines if ln.text.strip()]
        if self.kind == "text":
            return [ln for ln in str(self.payload).splitlines() if ln.strip()]
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
# Page content → (kind, text) elements, with line-level junk filtering
# ---------------------------------------------------------------------------

def direct_text_elements(text: str, drop_line: DropLine) -> list[tuple[str, str]]:
    raw_lines = [clean.normalize_arabic(ln) for ln in text.splitlines()]
    raw_lines = [ln for ln in raw_lines if ln]
    lines = [ln for i, ln in enumerate(raw_lines)
             if not drop_line(ln, i < 2 or i >= len(raw_lines) - 2)]
    paragraphs: list[str] = []
    buffer: list[str] = []
    for line in lines:
        buffer.append(line)
        if line and line[-1] in TERMINAL_PUNCT:
            paragraphs.append(" ".join(buffer))
            buffer = []
    if buffer:
        paragraphs.append(" ".join(buffer))
    out: list[tuple[str, str]] = []
    for par in paragraphs:
        kind = "h2" if looks_like_heading_text(par) else "p"
        out.append((kind, par))
    return out


def ocr_page_elements(page: OcrPage, keep_diacritics: bool,
                      drop_line: DropLine) -> list[tuple[str, str]]:
    visible = [ln for ln in page.lines if ln.text.strip()]
    kept = [ln for i, ln in enumerate(visible)
            if not drop_line(clean.normalize_arabic(ln.text, keep_diacritics),
                             i < 2 or i >= len(visible) - 2)]
    filtered = OcrPage(page_no=page.page_no, size=page.size, lines=kept)

    # Poetry blocks keep one bayt per line; everything else flows as prose.
    verse_idx = poetry.detect_verse_lines(filtered)
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(filtered.lines):
        if i in verse_idx:
            j = i
            while j < len(filtered.lines) and j in verse_idx:
                text = clean.normalize_arabic(poetry.verse_text(filtered.lines[j]),
                                              keep_diacritics)
                if text:
                    out.append(("verse", text))
                j += 1
            i = j
            continue
        j = i
        while j < len(filtered.lines) and j not in verse_idx:
            j += 1
        prose = OcrPage(page_no=page.page_no, size=page.size, lines=filtered.lines[i:j])
        heading_idx = set(detect_heading_lines(prose))
        heading_texts = {clean.normalize_arabic(prose.lines[k].text, keep_diacritics)
                         for k in heading_idx}
        for par in page_paragraphs(prose):
            normalized = clean.normalize_arabic(par, keep_diacritics)
            if not normalized:
                continue
            is_heading = normalized in heading_texts or (
                len(normalized.split()) <= 8 and looks_like_heading_text(normalized)
            )
            out.append(("h2" if is_heading else "p", normalized))
        i = j

    # Quranic quotes: restore ornate brackets when a citation cue is adjacent,
    # and honour explicit attribution lines like 'قرآن كريم' beneath a quote.
    final: list[tuple[str, str]] = []
    for n, (kind, text) in enumerate(out):
        if kind == "p":
            next_text = out[n + 1][1] if n + 1 < len(out) else ""
            if poetry.QURAN_ATTRIBUTION_RE.match(next_text):
                final.append(("quran", poetry.attributed_quran(text)))
                continue
            window = " ".join(t for _, t in out[max(0, n - 1): n + 2])
            has_cue = bool(poetry.QURAN_CUE_RE.search(window))
            text, dominated = poetry.mark_quran(text, has_cue)
            if dominated:
                kind = "quran"
        final.append((kind, text))
    return final


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
        direct_text: dict[int, str] = {}
        if opts.mode == "auto" and opts.text_layer != "never":
            for idx in indices:
                text = pdf.extract_text(idx)
                stripped = text.strip()
                if len(stripped) >= TEXT_LAYER_MIN_CHARS:
                    direct_text[idx] = stripped
            # Quality gate: many scanned books embed a *broken* text layer
            # (lam-alef ligatures lose the alef, hamza forms scramble).
            # When the sampled text looks corrupted, ignore the whole layer
            # and OCR instead — unless the user forces --text-layer always.
            if direct_text and opts.text_layer == "auto":
                sample = "\n".join(list(direct_text.values())[:10])
                if clean.looks_corrupted_arabic(sample):
                    direct_text.clear()

    # 2. Recognition pass: text layer / OCR / image per page.
    ocr_indices = [i for i in indices if i not in direct_text]
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
        if idx in direct_text:
            pages_data.append(PageData(index=idx, kind="text", payload=direct_text[idx]))
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
        if data.kind == "ocr":
            data.elements = ocr_page_elements(data.payload, opts.ocr.keep_diacritics, drop_line)
        elif data.kind == "text":
            data.elements = direct_text_elements(str(data.payload), drop_line)

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

    # 5. Chapter assembly.
    heading_count = sum(1 for p in pages_data for k, _ in p.elements if k == "h2")
    chapters: list[Chapter] = []
    current = Chapter(title="")
    pages_in_chapter = 0
    use_headings = heading_count >= 2

    def flush() -> None:
        nonlocal current, pages_in_chapter
        if current.elements:
            chapters.append(current)
        current = Chapter(title="")
        pages_in_chapter = 0

    for data in pages_data:
        if data.kind == "image":
            current.elements.append(PageImage(data.index, data.image_rel or ""))
        else:
            for kind, text in data.elements:
                if kind == "h2" and use_headings:
                    # Two-line headings arrive as consecutive h2 elements:
                    # merge them into one chapter title instead of opening an
                    # empty chapter per line.
                    only_heading_so_far = (
                        len(current.elements) == 1
                        and isinstance(current.elements[0], Paragraph)
                        and current.elements[0].kind == "h2"
                    )
                    if only_heading_so_far:
                        merged = f"{current.elements[0].text} {text}".strip()
                        current.elements[0] = Paragraph(merged, "h2")
                        current.title = clean.clean_heading(merged) or current.title
                    else:
                        flush()
                        current.title = clean.clean_heading(text) or text
                        current.elements.append(Paragraph(text, "h2"))
                else:
                    current.elements.append(Paragraph(text, kind))
        pages_in_chapter += 1
        if not use_headings and pages_in_chapter >= max(1, opts.split_every):
            flush()
    flush()

    if not chapters:
        chapters = [Chapter(title="", elements=[Paragraph("(لم يُتعرف على نص)", "p")])]
    for i, chapter in enumerate(chapters):
        if not chapter.title:
            chapter.title = f"قسم {i + 1}"

    title = opts.meta.title or default_title(pdf_path)
    book = Book(title=title, author=opts.meta.author, language=opts.meta.language,
                chapters=chapters)
    text_dir = work.stage_dir("text")
    book.save(text_dir / "book.json")

    # 6. Build EPUB volume(s).
    from .pipeline import _volume_chunks, _volume_path

    font_files = resolve_fonts(opts.font)
    chunks = _volume_chunks(chapters, opts.split_volumes)
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
