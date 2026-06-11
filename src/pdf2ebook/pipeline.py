"""Pipeline orchestration: cached stages → EPUB output.

Pages stream one at a time so 2,000+ page books convert in constant memory.
Every stage writes into the work dir and is skipped on re-runs when its
settings (and the source PDF) are unchanged.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from PIL import Image

from .cbz import write_cbz
from .config import PipelineOptions, parse_page_range
from .devices import get_profile
from .epub.fixedlayout import build_image_epub
from .pdfio import PdfRasterizer
from .preprocess.pipeline import preprocess_for_image
from .workdir import WorkDir

# progress callback: (stage, done, total)
Progress = Callable[[str, int, int], None]


@dataclass
class ConversionResult:
    outputs: list[Path] = field(default_factory=list)
    pages_total: int = 0
    pages_ocr: int = 0
    pages_direct_text: int = 0
    pages_image_fallback: int = 0
    stripped_lines: list[str] = field(default_factory=list)
    mean_confidences: list[float] = field(default_factory=list)


def default_work_dir(pdf_path: Path) -> Path:
    return pdf_path.with_name(pdf_path.stem + ".workdir")


def default_title(pdf_path: Path) -> str:
    title = pdf_path.stem
    title = re.sub(r"(?i)noor-book\.com\s*", "", title)
    return title.strip(" -_") or pdf_path.stem


def _volume_chunks(items: list, volumes: int) -> list[list]:
    volumes = max(1, volumes)
    if volumes == 1:
        return [items]
    size = -(-len(items) // volumes)  # ceil division
    return [items[i:i + size] for i in range(0, len(items), size)]


def _volume_path(out_path: Path, index: int, total: int) -> Path:
    if total == 1:
        return out_path
    return out_path.with_name(f"{out_path.stem} - {index + 1}{out_path.suffix}")


# ---------------------------------------------------------------------------
# Stage: rasterize PDF pages → raw/ PNGs
# ---------------------------------------------------------------------------

def extract_pages(
    pdf: PdfRasterizer,
    work: WorkDir,
    indices: list[int],
    dpi: int,
    force: bool = False,
    progress: Progress | None = None,
) -> list[Path]:
    settings = {"dpi": dpi, "pages": indices[:1] + indices[-1:] + [len(indices)]}
    if force:
        work.invalidate("raw")
    work.begin_stage("raw", settings)
    out_paths: list[Path] = []
    for n, idx in enumerate(indices):
        out = work.page_path("raw", idx)
        if not out.exists():
            img = pdf.render_page(idx, dpi=dpi, grayscale=True)
            img.save(out, format="PNG")
        out_paths.append(out)
        if progress:
            progress("extract", n + 1, len(indices))
    return out_paths


# ---------------------------------------------------------------------------
# Stage: preprocess for image mode → pre-image/ PNGs
# ---------------------------------------------------------------------------

def preprocess_image_pages(
    work: WorkDir,
    raw_paths: list[Path],
    width: int,
    height: int,
    style: str,
    force: bool = False,
    progress: Progress | None = None,
) -> list[Path]:
    settings = {"width": width, "height": height, "style": style, "v": 1}
    if force:
        work.invalidate("pre-image")
    work.begin_stage("pre-image", settings)
    out_paths: list[Path] = []
    for n, src in enumerate(raw_paths):
        out = work.root / "pre-image" / src.name
        if not out.exists():
            with Image.open(src) as img:
                processed = preprocess_for_image(img, width, height, style=style)
                processed.save(out, format="PNG")
        out_paths.append(out)
        if progress:
            progress("preprocess", n + 1, len(raw_paths))
    return out_paths


# ---------------------------------------------------------------------------
# Image mode
# ---------------------------------------------------------------------------

def run_image_mode(
    pdf_path: Path,
    out_path: Path,
    opts: PipelineOptions,
    progress: Progress | None = None,
) -> ConversionResult:
    result = ConversionResult()
    profile = get_profile(opts.image.device)
    width = opts.image.width or profile.width
    height = opts.image.height or profile.height

    work = WorkDir(opts.work_dir or default_work_dir(pdf_path), pdf_path)
    with PdfRasterizer(pdf_path) as pdf:
        indices = parse_page_range(opts.pages, pdf.page_count)
        result.pages_total = len(indices)
        force_extract = opts.force in ("extract", "all")
        force_pre = opts.force in ("preprocess", "all") or force_extract
        raw_paths = extract_pages(pdf, work, indices, opts.dpi, force_extract, progress)
        pre_paths = preprocess_image_pages(work, raw_paths, width, height,
                                           opts.image.style, force_pre, progress)

    title = opts.meta.title or default_title(pdf_path)
    chunks = _volume_chunks(pre_paths, opts.split_volumes)
    done_pages = 0
    total_pages = len(pre_paths)
    for vol, chunk in enumerate(chunks):
        vol_title = title if len(chunks) == 1 else f"{title} — {vol + 1}"
        vol_out = _volume_path(out_path, vol, len(chunks))

        def page_progress(i: int, _base=done_pages) -> None:
            if progress:
                progress("epub", _base + i, total_pages)

        build_image_epub(
            chunk, vol_out, vol_title, author=opts.meta.author, language=opts.meta.language,
            style=opts.image.style, layout=opts.image.layout,
            viewport=(width, height) if width and height else None,
            progress=page_progress,
        )
        result.outputs.append(vol_out)
        done_pages += len(chunk)

        if opts.image.cbz:
            cbz_out = vol_out.with_suffix(".cbz")
            write_cbz(chunk, cbz_out)
            result.outputs.append(cbz_out)

    if opts.clean:
        work.cleanup()
    return result


# ---------------------------------------------------------------------------
# Inspection (used by `pdf2ebook inspect` and the web UI)
# ---------------------------------------------------------------------------

def inspect_pdf(pdf_path: Path, sample_pages: int = 5) -> dict:
    with PdfRasterizer(pdf_path) as pdf:
        n = pdf.page_count
        sample = sorted({0, 2, 5, n // 2, n - 1} & set(range(n)))[:sample_pages]
        text_chars = [len(pdf.extract_text(i).strip()) for i in sample]
        w, h = pdf.page_size_pts(min(n // 2, n - 1))
        meta = pdf.metadata()

    avg_chars = sum(text_chars) / max(1, len(text_chars))
    has_text_layer = avg_chars > 200
    return {
        "file": pdf_path.name,
        "pages": n,
        "page_size_pts": (round(w), round(h)),
        "avg_sample_text_chars": round(avg_chars),
        "has_text_layer": has_text_layer,
        "title": meta.get("title", ""),
        "author": meta.get("author", ""),
        "recommendation": (
            "Text layer found: '--mode auto' will extract it directly (no OCR needed)."
            if has_text_layer
            else "Scanned book: use '--mode auto' (OCR) or '--mode image'."
        ),
    }
