"""Minimal EPUB 3 container writer.

An EPUB is a zip whose first entry must be an *uncompressed* `mimetype` file,
followed by META-INF/container.xml pointing at the OPF package document.
Hand-rolling this (instead of ebooklib, which is AGPL) gives full control over
RTL metadata.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

CONTAINER_XML = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""


class EpubContainer:
    def __init__(self, out_path: Path):
        self.out_path = Path(out_path)
        self._zip = zipfile.ZipFile(self.out_path, "w")
        self._zip.writestr(
            zipfile.ZipInfo("mimetype"), "application/epub+zip", compress_type=zipfile.ZIP_STORED
        )
        self.add("META-INF/container.xml", CONTAINER_XML)

    def add(self, name: str, data: bytes | str, compress: bool = True) -> None:
        if isinstance(data, str):
            data = data.encode("utf-8")
        ctype = zipfile.ZIP_DEFLATED if compress else zipfile.ZIP_STORED
        self._zip.writestr(name, data, compress_type=ctype)

    def add_file(self, name: str, src: Path, compress: bool = True) -> None:
        self.add(name, src.read_bytes(), compress=compress)

    def close(self) -> None:
        self._zip.close()

    def __enter__(self) -> "EpubContainer":
        return self

    def __exit__(self, exc_type, *exc_info) -> None:
        self.close()
        if exc_type is not None and self.out_path.exists():
            self.out_path.unlink()
