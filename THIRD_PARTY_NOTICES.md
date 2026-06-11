# Third-party notices

## Bundled

- **Amiri font** (`src/pdf2ebook/fonts/Amiri-Regular.ttf`) — © The Amiri Project
  (https://github.com/aliftype/amiri), licensed under the SIL Open Font License 1.1
  (`src/pdf2ebook/fonts/OFL.txt`). The OFL permits bundling and embedding in documents.

## Downloaded at runtime

- **Tesseract language data** (`ara.traineddata` and friends) — from
  https://github.com/tesseract-ocr/tessdata_best, Apache-2.0. Downloaded into the
  per-user data directory on first OCR run when the language is not installed system-wide.

## Optional dependencies

- **Surya OCR** (`pip install "arabic-pdf2ebook[surya]"`) — code Apache-2.0; **model
  weights ship under a modified AI Pubs Open Rail-M license**: free for research, personal
  use, and organizations under the revenue threshold stated by the authors. See
  https://github.com/datalab-to/surya for the current terms. Surya is never required —
  the core tool is fully functional without it.

## Key runtime dependencies (all permissive licenses)

| Package | License |
|---|---|
| pypdfium2 / PDFium | BSD-3-Clause / Apache-2.0 |
| pytesseract | Apache-2.0 |
| Tesseract OCR engine (system install) | Apache-2.0 |
| opencv-contrib-python-headless | Apache-2.0 |
| numpy | BSD-3-Clause |
| Pillow | MIT-CMU |
| typer, rich, fastapi, uvicorn | MIT / BSD-3-Clause |

This project deliberately avoids AGPL-licensed libraries (PyMuPDF, ebooklib).
