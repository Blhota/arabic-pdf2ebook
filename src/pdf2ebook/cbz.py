"""CBZ output for comic-style readers (KOReader and friends)."""

from __future__ import annotations

import zipfile
from pathlib import Path


def write_cbz(page_paths: list[Path], out_path: Path) -> Path:
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, src in enumerate(page_paths):
            zf.write(src, f"page_{i + 1:04d}{src.suffix}")
    return out_path
