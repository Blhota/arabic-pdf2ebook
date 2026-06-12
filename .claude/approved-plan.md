# Web UI: Self-explanatory form fields (mode hints + device gating)

## Context

The web UI form (Mode, Device, Split volumes) gives no indication of what each option actually does. The Mode dropdown options ("نص (OCR) — Text, resizable" / "صور محسّنة — Cleaned page images") are terse, and the Device selector — which only applies in image mode — is always active, even in text mode where the backend silently ignores it. The user wants the form to be self-explanatory.

Decisions made with the user:
- Add a small bilingual helper-text line under **every** field (Mode hint is dynamic, updating with the selection; Device and Split volumes hints are static).
- **Dim + disable** the Device field when Text (OCR) mode is selected, with its hint explaining it only applies in image mode.

## File to modify

`src/pdf2ebook/webui/static/index.html` — single self-contained page (vanilla HTML/CSS/JS, RTL, bilingual "Arabic — English" em-dash convention).

Key existing landmarks:
- Mode select: `#mode` (lines ~54-60), Device select: `#device` (~61-70), Volumes input: `#volumes` (~71-74)
- CSS design tokens at top of `<style>` (`--accent: #0d7a5f`, label style `font-size: 0.85rem; color: #555`)
- Existing `.warn` banner pattern for the Tesseract warning — reuse its tone, not its style (hints are informational, not warnings)

## Changes

### 1. CSS — hint and disabled-field styles

Add to the `<style>` block:

```css
.hint { font-size: 0.78rem; color: #777; margin-top: 0.25rem; line-height: 1.45; }
.field.disabled { opacity: 0.45; }
.field.disabled select { pointer-events: none; }
```

### 2. HTML — hint elements under each field

- Under `#mode`: `<div class="hint" id="mode-hint"></div>` (text filled by JS, dynamic).
- Under `#device` (give its wrapper `id="device-field"`):
  `يُستخدم في وضع الصور فقط — لتحديد مقاس الصفحة لشاشة قارئك — Only used in image mode; sets page size for your e-reader screen`
- Under `#volumes`:
  `قسّم الكتب الكبيرة إلى عدة ملفات EPUB — Split large books into several EPUB files`

### 3. JS — dynamic mode hint + device gating

Add a small script section (near the existing `stageNames` logic):

```js
const modeHints = {
  auto: 'يحوّل الصفحات إلى نص قابل لتغيير الحجم والبحث (يستخدم OCR عند الحاجة) — مناسب للروايات والنثر — Converts pages to resizable, searchable text (OCR when needed). Best for prose.',
  image: 'يحافظ على شكل الصفحة الأصلي كصور منظّفة — مناسب للجداول والرسوم — Keeps the original page layout as cleaned images. Best for tables and diagrams.'
};
function updateModeUI() {
  const mode = document.getElementById('mode').value;
  document.getElementById('mode-hint').textContent = modeHints[mode];
  const deviceField = document.getElementById('device-field');
  deviceField.classList.toggle('disabled', mode !== 'image');
  document.getElementById('device').disabled = mode !== 'image';
}
document.getElementById('mode').addEventListener('change', updateModeUI);
updateModeUI(); // set initial state on load
```

Note: disabling the `<select>` is safe here — the request is built manually with `fd.append('device', document.getElementById('device').value)` (index.html:144), and `.value` is readable on a disabled select. The backend ignores device in text mode anyway.

### 4. Device label cleanup

Change `الجهاز — Device (image mode)` to just `الجهاز — Device`, since the hint + dimming now communicate the image-mode-only relationship more clearly than the parenthetical.

## Verification

1. Run the web UI: `python -m pdf2ebook.webui` (or however `app.py` is launched — check `pyproject.toml` entry points) and open `http://127.0.0.1:8765`.
2. On load (default mode = text/OCR): mode hint shows the text-mode description; Device field is dimmed/disabled with its hint visible.
3. Switch Mode to image: hint text swaps; Device field becomes active.
4. Run a conversion in each mode to confirm the request still sends valid `mode`/`device` values and the job completes.
5. Visually check RTL rendering: hints align right, em-dash bilingual pattern reads correctly.
