# Reading Arabic on your device — دليل الأجهزة

Every EPUB this tool produces **embeds the Amiri Arabic font inside the book file**, so most
readers need nothing at all. This page covers each device family, including the ones that need
a little help.

كل كتاب EPUB تنتجه الأداة يحمل خط أميري بداخله، فمعظم الأجهزة لا تحتاج أي خطوة إضافية.

---

## Phones & tablets (Apple Books, Google Play Books, Moon+ Reader, …)

Nothing to do — open the EPUB and read. The embedded font renders the Arabic even on devices
with no Arabic fonts installed.

لا شيء مطلوب — افتح الكتاب واقرأ.

## Kobo

1. Open the book, tap the page → **Aa** (fonts) → set font to **Publisher Default** /
   "use publisher fonts". Done.
2. If your Kobo ignores embedded fonts: run `pdf2ebook fonts export`, connect the Kobo over
   USB, and copy `Amiri-Regular.ttf` into the `fonts` folder on the device (create the folder
   if it doesn't exist). Then pick Amiri in the reading menu.

## Kindle

Modern Kindles: email the EPUB to your device with
[Send-to-Kindle](https://www.amazon.com/sendtokindle) — Amazon converts it and Arabic renders
with Amazon's fonts. Old Kindles have weak Arabic support; prefer `--mode image`.

## CrossPoint readers (Xteink X3 / X4) — قارئات CrossPoint

CrossPoint's built-in fonts **contain no Arabic letters yet** (you will see boxes ▯▯▯), and the
firmware doesn't join Arabic letters yet either. Until upstream support lands, this tool ships
everything needed:

**First time only — set up the reader (do this ONCE, never again):**

```
# on the reader: enable Wi-Fi transfer mode (it shows an address like 192.168.1.50)
pdf2ebook fonts install --host 192.168.1.50
# then on the reader: Settings → Reader → Font Family → Amiri
```

The font stays on the reader's SD card permanently — you never reinstall it, no matter how
many books you add. (Only exception: you delete it or swap SD cards.)

**Every book after that — just two steps:**

```
pdf2ebook convert "كتابي.pdf" --preshape
pdf2ebook send "كتابي.epub" --host 192.168.1.50
```

The same buttons exist in the web page (`pdf2ebook ui`): the checkbox
"توافق CrossPoint" when converting, and "ثبّت الخط العربي" next to Send.

**What to expect:** letters appear connected (the `--preshape` option bakes the joining into
the text, and the installed font carries the joined letter shapes). Line *direction* may still
look wrong until CrossPoint ships its right-to-left update (it is in active development).
Two alternatives that work today:

- **Image mode** — `pdf2ebook convert "كتابي.pdf" --mode image --device xteink-x4` — the page
  is shown exactly as printed; 100% correct Arabic, just no font resizing.
- **papyrix-reader** — a community firmware fork with Arabic script support.

**Removing the font:** delete the `Amiri_*.cpfont` files from the hidden `/.fonts/` folder on
the SD card. Nothing is flashed; the reader is unchanged.

ملخص بالعربية: قارئات CrossPoint لا تحتوي على حروف عربية بعد. حوّل كتابك مع خيار
`--preshape`، ثبّت الخط مرة واحدة بأمر `pdf2ebook fonts install`، اختر خط Amiri من إعدادات
القارئ، وأرسل الكتاب. وإن لم تعجبك النتيجة فوضع الصور (`--mode image`) يعمل دائمًا بشكل مثالي.

## KOReader (Kobo/Kindle/Android jailbreak community firmware)

Uses embedded fonts automatically; full Arabic shaping built in. Nothing to do.
