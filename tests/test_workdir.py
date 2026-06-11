from __future__ import annotations

from pdf2ebook.workdir import WorkDir


def test_stage_caching_and_invalidation(tmp_path, tiny_pdf):
    work = WorkDir(tmp_path / "wd", tiny_pdf)
    settings = {"dpi": 300}
    stage = work.begin_stage("raw", settings)
    (stage / "page_0001.png").write_bytes(b"fake")
    assert work.stage_valid("raw", settings)

    # Same settings: file survives.
    work.begin_stage("raw", settings)
    assert (stage / "page_0001.png").exists()

    # Changed settings: stage is wiped.
    work.begin_stage("raw", {"dpi": 200})
    assert not (stage / "page_0001.png").exists()
    assert work.stage_valid("raw", {"dpi": 200})
    assert not work.stage_valid("raw", settings)


def test_pdf_change_clears_cache(tmp_path, tiny_pdf):
    work = WorkDir(tmp_path / "wd", tiny_pdf)
    stage = work.begin_stage("raw", {"dpi": 300})
    (stage / "page_0001.png").write_bytes(b"fake")

    # Same PDF re-opened: cache survives.
    WorkDir(tmp_path / "wd", tiny_pdf)
    assert (stage / "page_0001.png").exists()

    # Different content at the same path: cache is wiped.
    other = tmp_path / "other.pdf"
    other.write_bytes(tiny_pdf.read_bytes() + b"x")
    WorkDir(tmp_path / "wd", other)
    assert not (stage / "page_0001.png").exists()
