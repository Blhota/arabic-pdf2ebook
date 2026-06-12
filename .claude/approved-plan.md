# Plan: Arabic on CrossPoint (Xteink X4) — pre-shaped text + custom SD font

## Context

The user's text-mode EPUBs show **boxes and symbols** on their Xteink X4 running CrossPoint.
Root cause (confirmed from CrossPoint's own discussions #1757/#1693): the firmware's built-in
fonts contain **no Arabic glyphs**, and Arabic **shaping** (contextual letter joining) is not
implemented yet; RTL line rendering is "pretty much done" upstream but unreleased. The EPUB
itself is correct (renders fine in Calibre/phone apps). CrossPoint supports **custom SD-card
fonts**: a TTF uploaded through its web admin is converted to its bitmap format.

User decision: pursue the **custom SD font + pre-shaping** experiment — our tool will offer an
opt-in mode that bakes the letter-joining into the text itself (Arabic Presentation Forms,
U+FB50–FEFF), so a renderer that just draws glyphs can still show connected Arabic once it has
a font containing those glyphs. Amiri (already bundled at `src/pdf2ebook/fonts/Amiri-Regular.ttf`)
maps the presentation-form codepoints, so it's the font to upload to the reader.

## The self-service user journey (what the README must teach)

Guiding requirement from the user: **no human assistance in the loop** — anyone on the
internet installs the program and the README shows them the complete path. The program
ships the font ready-made; users never run font-conversion tooling.

The documented journey for a CrossPoint (Xteink X4) owner becomes:

```
1. pdf2ebook convert "كتابي.pdf" --preshape          # book with pre-joined letters
2. Turn on Wi-Fi transfer on the reader (it shows an address like 192.168.1.50)
3. pdf2ebook fonts install --host 192.168.1.50       # one-time: Arabic font → reader
   pdf2ebook send "كتابي.epub" --host 192.168.1.50   # the book itself
4. On the reader: Settings → Reader → Font Family → Amiri. Open the book.
```

(Equivalent buttons exist in the web page, and `pdf2ebook fonts export` covers USB/manual
copy and other devices like Kobo.) Removing the font later = deleting the files from
`/.fonts/` on the SD card; nothing is flashed, fully reversible.

To make step 3 possible without any user-side tooling, the **build process** (not the user)
pre-converts the bundled `Amiri-Regular.ttf` to CrossPoint's `.cpfont` format once — using
CrossPoint's own `fontconvert_sdcard.py` with Unicode intervals covering Latin + Arabic
(0600–06FF) + **Arabic Presentation Forms (FB50–FDFF, FE70–FEFF)** at sizes 12,14,16,18 —
and the results are committed to the repo so they ship inside the pip package and the .exe.

## Changes

1. **Pre-shaping option** (off by default — proper readers like Kobo/Apple must keep normal text):
   - Add dependency `arabic-reshaper` (MIT, pure Python) in `pyproject.toml`.
   - New `preshape: bool = False` on `PipelineOptions` (`src/pdf2ebook/config.py`).
   - In `src/pdf2ebook/ocrmode.py` `run_text_mode`: when `opts.preshape`, transform every
     element text AND chapter titles through `arabic_reshaper.reshape()` just before the Book
     is built (after all cleanup — reshaping is the final transform). No bidi visual
     reordering (it breaks reflowable line wrapping; CrossPoint's upcoming RTL handles direction).
   - CLI: `--preshape` flag on `convert` (`src/pdf2ebook/cli.py`), help text explaining it's
     for simple readers (CrossPoint) only.
   - Web UI: checkbox in `src/pdf2ebook/webui/static/index.html` ("توافق CrossPoint — pre-join
     letters for simple readers") posted as a form field; plumb through `webui/app.py`.
   - Note in `xteink-x4` profile notes (`devices.py`) pointing at the flag.

2. **Fonts as a first-class deliverable** (user request: the font ships ready-to-install for
   ANY reader that lacks Arabic — Kobo, Apple, CrossPoint…, and stays packaged with the text):
   - EPUBs **already embed Amiri inside the book file** — keep that as the default
     (`--font amiri`); on Apple Books, Kobo, KOReader and most apps the book carries its own
     Arabic font and renders even on devices with no Arabic fonts installed.
   - Pre-convert Amiri to CrossPoint's `.cpfont` format once (sizes 12,14,16,18, intervals
     incl. presentation forms) and commit the output to `src/pdf2ebook/fonts/cpfont/` so it
     ships inside the pip package and the .exe — no conversion tooling needed by users.
   - New CLI command group `pdf2ebook fonts`:
     - `pdf2ebook fonts export [DIR]` — writes ready-to-install font packages to a folder:
       `Amiri-Regular.ttf` (copy to a Kobo's `/fonts` folder or any reader that accepts TTF)
       plus the `cpfont/` set for CrossPoint SD cards, with a small README.txt (AR+EN).
     - `pdf2ebook fonts install --host <reader-ip>` — uploads the `.cpfont` files over Wi-Fi
       to the CrossPoint reader's `/.fonts/` directory (reuses `send.py`'s upload with its
       existing `dest_path` parameter).
   - Web UI: a small "تثبيت الخط على القارئ — Install font on reader" button next to Send.

3. **Documentation** — `docs/devices.md` (new): per-device Arabic guide:
   - **Apple Books / Android-iPhone apps / Kobo / KOReader**: nothing to install — the EPUB
     embeds Amiri inside the book file; on Kobo enable "use publisher fonts". For readers
     that ignore embedded fonts: `pdf2ebook fonts export` → copy the TTF to the reader's
     fonts folder over USB.
   - **CrossPoint (Xteink X3/X4)**: why boxes appear (no Arabic in built-in fonts; shaping
     not shipped); steps: `pdf2ebook fonts install --host <ip>` → on the reader Settings →
     Reader → Font Family → Amiri → convert the book with `--preshape` → send. Expectations:
     letters join; line direction may stay wrong until CrossPoint's RTL release lands; image
     mode (`--mode image --device xteink-x4`) remains the guaranteed path today;
     papyrix-reader fork as alternative firmware with Arabic support.
   - Link this from README.md + README.ar.md (short paragraph each).

4. **Tests** (new `tests/test_preshape.py` + extend `tests/test_cli.py`):
   - reshaped output contains presentation-form codepoints (U+FB50–FEFF) and joins lam-alef,
   - `--preshape` plumbing: convert tiny fixture with flag → chapter xhtml contains
     presentation forms; without flag → plain Arabic block only,
   - `fonts export` writes the TTF + cpfont set + bilingual README.txt.

5. Release as **v0.1.2** (version bump, push, tag — release automation is already live).

## Verification

1. `pytest` suite green; `ruff` clean.
2. Rebuild the Inquisition book with `--preshape` from cached OCR (seconds); script-check the
   chapter XHTML contains U+FB50–FEFF glyphs and the EPUB still passes structure checks.
3. **README check**: the per-device section in README.md / README.ar.md / docs/devices.md
   must let a stranger complete the journey with no outside help — review it against the
   4-step journey above, in both languages.
4. **User hardware test** (the user follows the README exactly as a stranger would):
   `fonts install` + `--preshape` book on the X4. Expected: connected Arabic letters;
   possibly wrong line direction until upstream RTL ships. If illegible, the README's
   fallback (image mode for this device) already works. The result tells us what to report
   upstream to CrossPoint.

## Out of scope (noted for later)

- Bidi visual reordering for shaping-less LTR renderers (breaks reflow; revisit only if
  CrossPoint RTL stalls).
- Upstream contribution: offering CrossPoint test EPUBs/issue report — worth doing after the
  experiment yields data, with the user's go-ahead.
