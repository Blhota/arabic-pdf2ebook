# Plan: `arabic-pdf2ebook` — Scanned Arabic PDF → Universal EPUB Converter

## Context

The user reads old scanned Arabic books (Noor-Book / kotob.has.it PDFs) on a small e-ink reader (Xteink X4 + CrossPoint firmware) but the PDFs are image-only — text can't be enlarged or reflowed. Goal: a new **open-source Python CLI tool** (greenfield, empty folder `c:\GitHub\pdf arabic to ebook`) for GitHub, so **anyone with a scanned Arabic book can read it on any e-reader**.

**User decisions:** both conversion modes (OCR → reflowable EPUB, and image-optimization → image EPUB); free/local OCR (Tesseract default, Surya optional extra); **standard EPUB 3 as the only output format** (universal: Kobo, Android/iOS apps, CrossPoint, modern Kindles via Send-to-Kindle); a **Wi-Fi send command** for CrossPoint devices; form factor = **PC program with a local web page UI** (double-click → browser opens → drag-and-drop PDF; looks like a website but runs entirely on the user's own computer — zero hosting costs) **plus CLI** for advanced users. Runs on the PC, never on the e-reader (e-readers are too weak for OCR).

**Inspection of the user's 12 sample books** (`C:\Users\hblho\OneDrive\سطح المكتب\Books`) found:
- 10/12 are image-only scans: PNG page images at ~310 DPI, small A5-ish pages (≈456×667 pts), zero text layer.
- Books range from 103 to **2,460 pages** → must stream page-at-a-time, be resumable, and support **volume splitting**.
- `أثار العباد.pdf` has a **real text layer** → tool must detect per-page text layers and extract directly (skip OCR).
- `محاكم التفتيش` has ~100 chars of text = just the `kotob.has.it` watermark layer → text-layer detection needs a per-page character threshold (>~200 chars/page = real text).
- One PDF is 0 bytes/corrupt → graceful error handling.

## How it will be used (distribution story)

**The owner uploads the repo to GitHub; from then on anyone can use it three ways:**

1. **One-command install (technical users)**: `pip install arabic-pdf2ebook` (published to PyPI via GitHub Actions on each tagged release) or `pip install git+https://github.com/<owner>/arabic-pdf2ebook`. Then:
   ```
   pdf2ebook convert "زاد المعاد.pdf"        →  زاد المعاد.epub  (works on any e-reader)
   pdf2ebook send "زاد المعاد.epub" --host 192.168.1.50   →  Wi-Fi upload to CrossPoint reader
   ```
2. **No-Python Windows executable (everybody else)**: GitHub Actions builds a standalone `pdf2ebook.exe` with PyInstaller and attaches it to every GitHub Release. Users download one file; **double-clicking it launches the local web UI** — the browser opens `http://127.0.0.1:8765` with a bilingual (Arabic/English, RTL) drag-and-drop page: drop PDF → pick Text/Image mode → Convert (live progress bar) → Download EPUB / Send over Wi-Fi. No Python required. It detects Tesseract or shows a friendly bilingual message linking the installer.
3. **README quick-start in Arabic and English** with screenshots, since the audience is Arabic-book readers worldwide. Output is standard EPUB 3 → readable on Kobo, Kindle (Send-to-Kindle), Apple Books, Android/iOS apps, KOReader, CrossPoint.

## Prior art (researched June 2026) — and what we borrow

- **OCRmyPDF** (Tesseract OCR layer → searchable PDF): best-in-class pipeline discipline — borrow page-at-a-time streaming, resumable stages, Tesseract integration patterns. Doesn't output EPUB.
- **KCC / Kindle Comic Converter** (user already uses it): borrow the product model — device profiles, e-ink image optimization, standalone PyInstaller `.exe` on GitHub Releases. No OCR/Arabic.
- **k2pdfopt**: validates the image-optimization mode (margin crop, contrast, device sizing). Dated, PDF-out only.
- **Tahweel (ieasybooks)**: Arabic scanned-PDF → TXT/DOCX via Google Drive cloud OCR. Proves Arabic demand; cloud OCR could become an optional third engine later. No EPUB, needs Google account.
- **marker + Surya (datalab)**: neural PDF→Markdown, Arabic supported — our optional `[surya]` high-accuracy engine; too heavy/license-restricted to be the default.
- **pdf-craft**: scanned-book → EPUB via DeepSeek OCR, GPU-centric, Arabic/RTL unproven.
- **Gap confirmed**: no existing tool does scanned-Arabic → proper RTL reflowable EPUB, locally, free, with a friendly UI. The RTL EPUB writer + Arabic text cleanup + local web UI + Wi-Fi send is this project's unique contribution.

## Key architecture decisions

| Decision | Choice | Why |
|---|---|---|
| License | Apache-2.0 | Permissive; avoids AGPL contamination |
| PDF rasterization + text-layer extraction | **pypdfium2** (BSD/Apache) | PyMuPDF is AGPL — rejected. pypdfium2 also exposes the text layer (`PdfTextPage`) for direct extraction |
| EPUB writer | **Hand-rolled zip writer** (~300 LOC) | ebooklib is AGPL; full control over RTL (`page-progression-direction="rtl"`, `dir="rtl"`, NCX fallback, font embedding) |
| Image processing | opencv-contrib-python-headless + NumPy + Pillow | Sauvola binarization native (`cv2.ximgproc`), CLAHE, deskew, denoise |
| OCR default | Tesseract 5 via pytesseract, **`ara` from tessdata_best**, `--oem 1` | Free, local; best-quality LSTM model |
| OCR optional | Surya as `[surya]` pip extra | Better on old prints; heavy torch dep; weights Open Rail-M (document in NOTICES) |
| CLI | Typer + Rich progress | Subcommands, typed flags, progress bars |
| Font | Amiri (SIL OFL, bundled), `--font none` option | Universal Arabic rendering; `none` keeps files small |
| Device profiles | **Generic by default** (`generic-6in` 758×1024); presets incl. `xteink-x4` (480×800); `--width/--height` override; `none` = keep source resolution | No single device baked in — universal output |
| Local web UI | **FastAPI + uvicorn** (MIT/BSD) serving one static vanilla-JS page; jobs run in a background thread over the same `pipeline.py` API; progress via polling `GET /api/jobs/{id}` | Looks like a website, runs locally for free; no JS build toolchain to maintain |

## Conversion modes (shared cached work dir)

- **`--mode auto` (default)**: per-page decision — page has real text layer (>200 chars) → extract text directly (perfect accuracy, free); otherwise OCR; OCR fails confidence gate → embed cleaned page image.
- **`--mode ocr`**: PDF → grayscale page PNGs (`raw/`, 300 DPI, one page at a time) → preprocess (deskew → denoise → CLAHE → Sauvola → autocrop → upscale-if-small) (`pre/`) → per-page OCR JSON (`ocr/<engine>/`) → text cleanup → chapter split → reflowable RTL EPUB.
- **`--mode image`**: PDF → `raw/` → preprocess (deskew → denoise → CLAHE → autocrop → scale to profile W×H) → EPUB of one full-width `<img>` per page (`--layout flow` default; `fixed` pre-paginated optional) + optional `--cbz`.
- **Work dir** (`<stem>.workdir/`): each stage cached with settings-hash invalidation; interrupted runs resume per-page (essential for 2,460-page books); switching OCR engine reuses extraction/preprocessing. `--force <stage>`, `--clean`.
- **Volume splitting**: `--split-volumes N` (and automatic suggestion when image-mode output would exceed ~80 MB) → `book - 1.epub`, `book - 2.epub` with continuous chapter numbering.

## Tesseract accuracy strategy (user-requested focus)

1. **tessdata_best `ara.traineddata`** + `--oem 1` (LSTM), documented install path `C:\Program Files\Tesseract-OCR\tessdata`.
2. **Preprocessing tuned for old paper**: Sauvola adaptive binarization (window 31, k 0.2), CLAHE (clip 2.0), fastNlMeans denoise, deskew (±5° cap), border/margin removal — the largest single accuracy lever.
3. **Correct PSM**: default `--psm 4` (single column) with `--psm` flag exposed; avoid auto-OSD confusion from ornate headers.
4. **Upscale small print** to ~35 px median character height (2× LANCZOS) before OCR; pass `--dpi 300` and `preserve_interword_spaces=1` to Tesseract.
5. **Multi-pass line rescue**: lines with conf < 50 are re-OCR'd with alternate binarization (Otsu, different Sauvola k) and the highest-confidence variant wins (`--rescue/--no-rescue`, default on).
6. **Confidence gating**: page `mean_conf < --min-conf 40` or <15 words → embed cleaned page image instead of garbage text; end-of-run report (pages OCR'd / direct-text / embedded, confidence histogram).
7. **`pdf2ebook preview`**: run extract+preprocess (+ optional OCR) on a small page range and open the intermediate PNGs + text, so the user tunes settings before a 2,460-page run.
8. Escalation path: `--engine surya` for stubborn books.

## Critical implementation details

- **Arabic text cleanup** (`textproc/`): strip tatweel + fold presentation forms (don't normalize hamza/alef — old orthography is content); auto-detect repeated header/footer lines on >40% of pages with fuzzy matching (catches mangled `http://kotob.has.it/` watermarks) + seed regexes + `--strip-pattern`; strip standalone page-number lines (incl. Arabic-Indic digits ٠-٩); paragraph rejoin via line-gap/RTL-indent/punctuation heuristics; merge paragraphs across page boundaries.
- **Chapter detection**: heading = tall (>1.4× median line height) + centered + ≤6 words, boosted by `^(الباب|الفصل|باب|فصل|مقدمة|تمهيد|خاتمة|فهرس)`; fallback one chapter per `--split-every 10` pages.
- **RTL EPUB correctness** (`epub/opf.py`): `<package ... xml:lang="ar" dir="rtl">`, `<dc:language>ar</dc:language>`, `<spine page-progression-direction="rtl" toc="ncx">`, every XHTML `lang="ar" dir="rtl"`, CSS `direction: rtl; text-align: justify;`, legacy `toc.ncx` alongside nav.xhtml.
- **OCR backend ABC** (`ocr/base.py`): `is_available() -> (bool, hint)`, `recognize(image_path) -> OcrPage` (words+conf+bboxes), registry with lazy imports; Tesseract discovery: `TESSERACT_CMD` env → PATH → `C:\Program Files\Tesseract-OCR\tesseract.exe`.
- **Wi-Fi send to CrossPoint** (`send.py` + `pdf2ebook send book.epub --host 192.168.x.x`): HTTP upload to the CrossPoint web file-transfer endpoint (multipart POST; verify exact endpoint against the crosspoint-reader GitHub source during implementation); `--host` remembered in a small user config. Uses stdlib `urllib`/`http.client` or `requests`.
- **Robustness**: corrupt/zero-byte PDFs → clear error, nonzero exit; encrypted PDFs detected in `inspect`.

## Repo layout (src layout)

```
pyproject.toml  LICENSE  THIRD_PARTY_NOTICES.md  README.md  docs/
src/pdf2ebook/
  cli.py            # Typer: convert / devices / preview / inspect / send / ui
  config.py  pipeline.py  workdir.py  pdfio.py  devices.py  book.py  cbz.py  send.py
  webui/app.py               # FastAPI: POST /api/convert, GET /api/jobs/{id}, GET /api/download/{id}, POST /api/send
  webui/static/index.html    # single bilingual RTL page (vanilla JS): drag-drop, mode picker, progress, download/send
  preprocess/ops.py          # pure ndarray fns: deskew, denoise, clahe, sauvola, autocrop, upscale, scale
  preprocess/pipeline.py     # preprocess_for_ocr/_for_image, detect_image_page
  ocr/base.py registry.py tesseract_backend.py surya_backend.py
  textproc/clean.py paragraphs.py chapters.py
  epub/zipwriter.py opf.py reflow.py fixedlayout.py templates.py
  fonts/Amiri-*.ttf OFL.txt
tests/  (preprocess, textproc, epub structure, workdir, CLI smoke; tiny 3-page fixtures)
tools/compare_engines.py
```

CLI: `pdf2ebook convert book.pdf --mode [auto|ocr|image] --engine [tesseract|surya] --device generic-6in --dpi 300 --pages 5-20 --psm 4 --min-conf 40 --rescue --split-volumes N --layout [flow|fixed] --cbz --font [amiri|scheherazade|none] --force <stage> --clean` plus `devices`, `preview`, `inspect`, `send`, and `ui` (starts the local web server and opens the browser; this is also the default action when `pdf2ebook.exe` is double-clicked with no arguments).

## Milestones

- **M1 — skeleton + image mode end-to-end**: pyproject, CLI, pdfio, workdir, preprocess, devices, zipwriter/opf/fixedlayout, cbz, tests. *Verify*: convert the 151-page Inquisition book `--mode image`; epubcheck passes; Calibre/Thorium show RTL page progression; kill mid-run and confirm resume; convert the 2,460-page book to confirm streaming + volume splitting.
- **M2 — OCR + auto mode (Tesseract)**: ocr base/registry/tesseract with PSM/upscale/rescue, text-layer direct extraction, textproc clean+paragraphs, book model, reflow EPUB, image-page fallback, fonts. *Verify*: epubcheck; Thorium RTL/justified/Amiri shaping; watermark + page numbers gone; spot-check 10 pages vs scan; `أثار العباد.pdf` uses direct text extraction (no OCR); `--force ocr` reuses raw/pre.
- **M3 — local web UI + Wi-Fi send**: `webui/` (FastAPI app + bilingual RTL drag-drop page, background job thread, progress polling, download), `pdf2ebook ui` command (auto-opens browser), `send` command + Send button tested against the CrossPoint device. *Verify*: drag the Inquisition PDF onto the page, watch live progress, download EPUB; `pdf2ebook send` lands the EPUB on the reader over Wi-Fi.
- **M4 — Surya backend + polish**: `[surya]` extra with batching, fuzzy repeated-line detection, chapter heuristics, `tools/compare_engines.py`. *Verify*: same book via `--engine surya`; comparison report shows where Surya beats Tesseract.
- **M5 — docs/packaging/CI/distribution**: bilingual (Arabic + English) README with quick-start and screenshots, Windows Tesseract walkthrough incl. tessdata_best, NOTICES (OFL, Surya weights), GitHub Actions: ruff/mypy/pytest (windows+ubuntu), epubcheck, pip-licenses, **PyPI publish on tag**, **PyInstaller standalone `pdf2ebook.exe`** (double-click → web UI) **attached to GitHub Releases**; `git init`, push to GitHub, v0.1.0 release. *Verify*: on a clean Windows machine with no Python, download the .exe from Releases, double-click, and convert a book following only the README.

## Dependencies

`pypdfium2>=5`, `pytesseract>=0.3.13`, `opencv-contrib-python-headless>=4.10`, `numpy`, `Pillow`, `typer`, `rich`; extra `surya = ["surya-ocr>=0.17,<1"]`; dev: pytest, ruff, mypy, epubcheck. Windows: Tesseract UB Mannheim installer + tessdata_best `ara.traineddata`; all Python deps have prebuilt wheels.

## Risks

- **Tesseract on old prints** (80–95% realistic even tuned): full mitigation stack above + per-page image fallback + Surya escalation + honest README.
- **CrossPoint Arabic shaping unproven**: test on hardware in M2; image mode is the guaranteed-working first-class fallback on every device.
- **AGPL**: avoided (pypdfium2 + hand-rolled EPUB); `pip-licenses` CI check.
- **2,460-page books**: strict page-at-a-time streaming (<100 MB RAM); work dir size documented (~0.3–1.5 GB for the largest book); `--dpi 200` escape hatch; volume splitting.
- **CrossPoint upload endpoint undocumented**: read the firmware source; if unstable, `send` degrades to printing manual-upload instructions.

## Verification (end-to-end)

1. `pdf2ebook inspect` on all 12 sample books — correct text-layer/scan detection, corrupt file reported cleanly.
2. `pdf2ebook convert "محاكم التفتيش...pdf" --mode image` → EPUB legible in Calibre, RTL page turn.
3. `pdf2ebook convert "محاكم التفتيش...pdf" --mode auto` → epubcheck clean; resizable Arabic text; watermark gone.
4. `pdf2ebook convert "البداية والنهاية ط بيت الأفكار.pdf" --mode image --split-volumes 4` → streams without memory issues.
5. `pdf2ebook send book.epub --host <reader-ip>` → book appears on the CrossPoint reader.
