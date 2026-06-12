from __future__ import annotations

from pdf2ebook.ocr.base import OcrLine, OcrPage, OcrWord
from pdf2ebook.textproc import poetry


def _line(text: str, y: int, words_with_x: list[tuple[str, int, int]] | None = None) -> OcrLine:
    if words_with_x is None:
        # synthesize evenly spaced word boxes
        words_with_x = []
        x = 100
        for w in text.split():
            words_with_x.append((w, x, len(w) * 14))
            x += len(w) * 14 + 8
    words = [OcrWord(w, 90.0, (x, y, width, 30)) for w, x, width in words_with_x]
    xs = [w.bbox[0] for w in words]
    x2s = [w.bbox[0] + w.bbox[2] for w in words]
    return OcrLine(words=words, bbox=(min(xs), y, max(x2s) - min(xs), 30))


RITHA = [
    "لكل شيء إذا ما تم نقصان",          # rhyme: ان
    "فلا يغر بطيب العيش إنسان",
    "هي الأمور كما شاهدتها دول",
    "من سره زمن ساءته أزمان",
    "وهذه الدار لا تبقي على أحد",
    "ولا يدوم على حال لها شان",
]


def test_detect_verse_lines_finds_rhymed_block():
    lines = [_line(t, 100 + i * 40) for i, t in enumerate(RITHA)]
    page = OcrPage(page_no=0, size=(800, 1200), lines=lines)
    verse = poetry.detect_verse_lines(page)
    assert len(verse) >= 4  # the rhymed block is detected


def test_prose_with_shared_single_letter_endings_not_verse():
    # Visual prose lines often end in ن by coincidence — must NOT be a poem.
    prose = [
        "وسيقت الأم والابنتان للإقرار الأخير وخشي السجان أن يعترفن",
        "بمقابلتهن فاعترف هو للكاهن بما كان منه وجمعه للثلاثة شفقة وعطفا عليهن",
        "ورجاه أن يسامحه ولكن سرعان ما قبض عليه وزج به في أعماق السجون",
        "وهو مكبل بالأغلال والقيود وحوكم أمام آباء الإيمان",
    ]
    lines = [_line(t, 100 + i * 40) for i, t in enumerate(prose)]
    page = OcrPage(page_no=0, size=(800, 1200), lines=lines)
    assert poetry.detect_verse_lines(page) == set()


def test_attributed_quran_restores_brackets():
    out = poetry.attributed_quran("قل هل يستوي الذين يعلمون والذين لا يعلمون» «أم هل تستوي الظلمات والنور*")
    assert out.startswith("﴿") and out.endswith("﴾")
    assert "«" not in out and "*" not in out
    assert poetry.QURAN_ATTRIBUTION_RE.match(" قرآن كريم ")
    assert poetry.QURAN_ATTRIBUTION_RE.match("سورة الرعد")
    assert not poetry.QURAN_ATTRIBUTION_RE.match("وكان من أمر القرآن الكريم في الأندلس")


def test_prose_not_marked_as_verse():
    prose = [
        "وكان المسلمون بالأندلس يستنجدون بسلاطين المغرب كلما اشتد الضغط عليهم.",
        "فكان أولئك السلاطين يرسلون إليهم الجيوش والأساطيل فيكشفون عنهم الضر.",
        "ولما ضعف أمر هؤلاء استولى ملوك الإسبان على جل حصون البلاد ومدنها الشهيرة.",
    ]
    lines = [_line(t, 100 + i * 40) for i, t in enumerate(prose)]
    page = OcrPage(page_no=0, size=(800, 1200), lines=lines)
    assert poetry.detect_verse_lines(page) == set()


def test_split_hemistichs_on_central_gap():
    # right hemistich words then a big central gap then left hemistich words
    words = [("هوى", 520, 60), ("له", 590, 40), ("أحد", 640, 60),
             ("دعا", 100, 60), ("الجزيرة", 170, 100), ("أمر", 280, 60)]
    line = _line("", 100, words_with_x=words)
    parts = poetry.split_hemistichs(line)
    assert parts is not None
    first, second = parts
    assert "الجزيرة" in second or "الجزيرة" in first  # both hemistichs present
    assert first != second


def test_verse_text_replaces_misread_divider():
    line = _line("دعا الجزيرة أمر | هوى له أحد", 100)
    text = poetry.verse_text(line)
    assert "|" not in text


def test_mark_quran_restores_ornate_brackets():
    text = "«قل هل يستوي الذين يعلمون والذين لا يعلمون»"
    out, dominated = poetry.mark_quran(text, has_cue_nearby=True)
    assert out.startswith("﴿") and out.endswith("﴾")
    assert dominated


def test_mark_quran_ignores_regular_quotes_without_cue():
    text = "وعرفه الإفرنج باسم ذي اللحية الحمراء «بارباروسا» وكانت له معرفة تامة"
    out, dominated = poetry.mark_quran(text, has_cue_nearby=False)
    assert out == text
    assert not dominated


def test_mark_quran_inline_quote_not_dominated():
    text = ("ودخلها ما دخلها من التغيير. " * 3) + "«إن الله لا يغير ما بقوم حتى يغيروا ما بأنفسهم» " + ("وقد رأيت أن الانقسام حدث في جسم الأمة. " * 3)
    out, dominated = poetry.mark_quran(text, has_cue_nearby=True)
    assert "﴿إن الله لا يغير" in out
    assert not dominated  # inline quote: brackets restored but paragraph stays prose
