"""Cached, resumable work directory.

Layout:
    <stem>.workdir/
        manifest.json          pdf sha256, page count, tool version
        raw/settings.json      rasterization settings + page PNGs
        pre-ocr/               preprocessed pages for OCR
        pre-image/             preprocessed pages for image mode
        ocr/<engine>/          per-page OcrPage JSON
        text/book.json         cleaned Book model

A stage is valid when its settings.json matches the current settings hash.
Individual pages are skipped when their output file already exists, so an
interrupted run resumes where it stopped.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from . import __version__


def _hash_settings(settings: dict) -> str:
    blob = json.dumps(settings, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _hash_file(path: Path, max_bytes: int = 64 * 1024 * 1024) -> str:
    """Hash the head of the file (whole file when small) — fast for 80 MB PDFs."""
    h = hashlib.sha256()
    h.update(str(path.stat().st_size).encode())
    with path.open("rb") as fh:
        h.update(fh.read(max_bytes))
    return h.hexdigest()


class WorkDir:
    def __init__(self, root: Path, pdf_path: Path):
        self.root = root
        self.pdf_path = pdf_path
        self.root.mkdir(parents=True, exist_ok=True)
        self._check_manifest()

    # -- manifest ------------------------------------------------------
    def _check_manifest(self) -> None:
        manifest_path = self.root / "manifest.json"
        pdf_hash = _hash_file(self.pdf_path)
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                manifest = {}
            if manifest.get("pdf_sha256") != pdf_hash:
                # Different source PDF: the whole cache is stale.
                for child in self.root.iterdir():
                    if child.is_dir():
                        shutil.rmtree(child)
                    elif child.name != "manifest.json":
                        child.unlink()
        manifest_path.write_text(
            json.dumps({"pdf_sha256": pdf_hash, "tool_version": __version__}, indent=2),
            encoding="utf-8",
        )

    # -- stages --------------------------------------------------------
    def stage_dir(self, stage: str) -> Path:
        d = self.root / stage
        d.mkdir(parents=True, exist_ok=True)
        return d

    def stage_valid(self, stage: str, settings: dict) -> bool:
        settings_path = self.root / stage / "settings.json"
        if not settings_path.exists():
            return False
        try:
            stored = json.loads(settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return False
        return stored.get("hash") == _hash_settings(settings)

    def begin_stage(self, stage: str, settings: dict) -> Path:
        """Return the stage dir, wiping it first when settings changed."""
        d = self.stage_dir(stage)
        if not self.stage_valid(stage, settings):
            for child in d.iterdir():
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
            (d / "settings.json").write_text(
                json.dumps({"hash": _hash_settings(settings), "settings": settings}, indent=2),
                encoding="utf-8",
            )
        return d

    def invalidate(self, stage: str) -> None:
        settings_path = self.root / stage / "settings.json"
        if settings_path.exists():
            settings_path.unlink()

    # -- page paths ----------------------------------------------------
    @staticmethod
    def page_name(index: int, ext: str = "png") -> str:
        return f"page_{index + 1:04d}.{ext}"

    def page_path(self, stage: str, index: int, ext: str = "png") -> Path:
        return self.root / stage / self.page_name(index, ext)

    def cleanup(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)
