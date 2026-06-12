"""Ready-to-install font packages for readers without Arabic support.

The package bundles the Amiri font twice:
- `fonts/Amiri-Regular.ttf` — embedded into every EPUB, and copyable to any
  reader that accepts TTF fonts (Kobo `fonts` folder, KOReader…)
- `fonts/cpfont/Amiri_*.cpfont` — pre-converted to CrossPoint's bitmap format
  (with Arabic Presentation Forms glyphs), installable over Wi-Fi.
"""

from __future__ import annotations

import shutil
from pathlib import Path

FONTS_DIR = Path(__file__).parent / "fonts"
CPFONT_DIR = FONTS_DIR / "cpfont"
CROSSPOINT_FONT_PATH = "/.fonts"

FONT_README = """\
Arabic font pack — arabic-pdf2ebook                حزمة الخط العربي
=================================================================

English
-------
Amiri-Regular.ttf
    For Kobo: connect the reader over USB and copy this file into the
    `fonts` folder on the device (create it if missing).
    For KOReader and most apps: same idea, or just rely on the font that is
    already embedded inside every EPUB this tool produces.

cpfont/Amiri_12..18.cpfont
    For CrossPoint readers (Xteink X3/X4): copy these files into the
    hidden `/.fonts/` folder on the SD card — or much easier, run:
        pdf2ebook fonts install --host <reader-ip>
    Then on the reader choose: Settings > Reader > Font Family > Amiri.
    Convert your books with `--preshape` so the letters join correctly.

العربية
-------
ملف Amiri-Regular.ttf
    لأجهزة كوبو: وصّل القارئ بالحاسوب وانسخ الملف إلى مجلد `fonts`
    في ذاكرة الجهاز (أنشئه إن لم يوجد).
    معظم التطبيقات لا تحتاج شيئًا: الخط مدمج أصلًا داخل كل كتاب EPUB
    تنتجه هذه الأداة.

ملفات cpfont/Amiri_*.cpfont
    لقارئات CrossPoint (مثل Xteink X4): انسخها إلى المجلد المخفي
    `/.fonts/` في بطاقة الذاكرة — أو ببساطة شغّل الأمر:
        pdf2ebook fonts install --host <عنوان-القارئ>
    ثم على القارئ: الإعدادات > القراءة > نوع الخط > Amiri.
    وحوّل كتبك مع خيار `--preshape` لتظهر الحروف متصلة.

License: Amiri is © The Amiri Project, SIL Open Font License 1.1 (OFL.txt).
"""


def cpfont_files() -> list[Path]:
    return sorted(CPFONT_DIR.glob("*.cpfont"))


def export_fonts(dest: Path) -> list[Path]:
    """Write the ready-to-install font pack into `dest`; returns written files."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in ("Amiri-Regular.ttf", "OFL.txt"):
        src = FONTS_DIR / name
        out = dest / name
        shutil.copy2(src, out)
        written.append(out)
    cp_dest = dest / "cpfont"
    cp_dest.mkdir(exist_ok=True)
    for src in cpfont_files():
        out = cp_dest / src.name
        shutil.copy2(src, out)
        written.append(out)
    readme = dest / "README.txt"
    readme.write_text(FONT_README, encoding="utf-8")
    written.append(readme)
    return written


def install_fonts_on_reader(host: str | None = None) -> tuple[str, int]:
    """Upload the cpfont set to a CrossPoint reader's /.fonts/ over Wi-Fi."""
    from .send import mkdir_on_reader, upload_file

    files = cpfont_files()
    if not files:
        raise RuntimeError("No .cpfont files bundled with this installation.")
    # The hidden fonts folder usually doesn't exist yet; the reader's upload
    # handler does not create parent folders itself.
    mkdir_on_reader(CROSSPOINT_FONT_PATH.strip("/"), host, parent="/")
    used_host = ""
    for f in files:
        used_host = upload_file(f, host, dest_path=CROSSPOINT_FONT_PATH)
    return used_host, len(files)
