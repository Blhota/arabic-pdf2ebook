"""PDF access built on pypdfium2 (permissive license, prebuilt wheels).

Provides page rasterization for the OCR/image pipelines and direct text-layer
extraction so born-digital pages can skip OCR entirely.
"""

from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image


class PdfError(RuntimeError):
    """Raised when the input PDF cannot be opened or rendered."""


class PdfRasterizer:
    def __init__(self, pdf_path: Path):
        self.path = Path(pdf_path)
        if not self.path.exists():
            raise PdfError(f"File not found: {self.path}")
        if self.path.stat().st_size == 0:
            raise PdfError(f"File is empty (0 bytes): {self.path.name}")
        try:
            self._doc = pdfium.PdfDocument(str(self.path))
        except Exception as exc:  # pdfium raises its own error types
            raise PdfError(f"Cannot open PDF '{self.path.name}': {exc}") from exc

    @property
    def page_count(self) -> int:
        return len(self._doc)

    def page_size_pts(self, index: int) -> tuple[float, float]:
        page = self._doc[index]
        try:
            return page.get_size()
        finally:
            page.close()

    def render_page(self, index: int, dpi: int = 300, grayscale: bool = True) -> Image.Image:
        page = self._doc[index]
        try:
            bitmap = page.render(scale=dpi / 72.0, grayscale=grayscale)
            img = bitmap.to_pil()
        except Exception as exc:
            raise PdfError(f"Failed to render page {index + 1}: {exc}") from exc
        finally:
            page.close()
        if grayscale and img.mode != "L":
            img = img.convert("L")
        return img

    def extract_text(self, index: int) -> str:
        page = self._doc[index]
        try:
            textpage = page.get_textpage()
            try:
                return textpage.get_text_bounded() or ""
            finally:
                textpage.close()
        except Exception:
            return ""
        finally:
            page.close()

    def metadata(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for key in ("Title", "Author"):
            try:
                value = self._doc.get_metadata_value(key)
            except Exception:
                value = None
            if value:
                out[key.lower()] = value
        return out

    def close(self) -> None:
        self._doc.close()

    def __enter__(self) -> "PdfRasterizer":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
