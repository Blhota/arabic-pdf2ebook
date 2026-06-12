from __future__ import annotations

import zipfile

from typer.testing import CliRunner

from pdf2ebook.cli import app
from pdf2ebook.config import parse_page_range

runner = CliRunner()


def test_devices_lists_profiles():
    result = runner.invoke(app, ["devices"])
    assert result.exit_code == 0
    assert "xteink-x4" in result.output


def test_inspect_detects_scan(tiny_pdf):
    result = runner.invoke(app, ["inspect", str(tiny_pdf)])
    assert result.exit_code == 0
    assert "text layer: no" in result.output


def test_convert_image_mode_end_to_end(tiny_pdf, tmp_path):
    out = tmp_path / "out.epub"
    result = runner.invoke(app, [
        "convert", str(tiny_pdf), str(out), "--mode", "image",
        "--work-dir", str(tmp_path / "wd"), "--clean",
    ])
    assert result.exit_code == 0, result.output
    assert out.exists()
    zf = zipfile.ZipFile(out)
    assert zf.read("mimetype") == b"application/epub+zip"
    assert not (tmp_path / "wd").exists()  # --clean removed the cache


def test_convert_rejects_bad_mode(tiny_pdf):
    result = runner.invoke(app, ["convert", str(tiny_pdf), "--mode", "banana"])
    assert result.exit_code == 2


def test_convert_empty_pdf_fails_cleanly(tmp_path):
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    result = runner.invoke(app, ["convert", str(empty), "--mode", "image"])
    assert result.exit_code == 1
    assert "empty" in result.output.lower()


def test_volume_chunks_balance_by_weight():
    from pdf2ebook.pipeline import _volume_chunks

    items = ["a", "b", "c", "d", "e"]
    weights = [100, 100, 1000, 100, 100]  # one giant chapter in the middle
    chunks = _volume_chunks(items, 3, weights)
    assert [x for chunk in chunks for x in chunk] == items  # order preserved
    assert 1 < len(chunks) <= 3
    totals = [sum(weights[items.index(x)] for x in chunk) for chunk in chunks]
    # no chunk should hold nearly everything while others are empty-ish
    assert max(totals) <= 1200 and min(totals) >= 100


def test_parse_page_range():
    assert parse_page_range("1-3", 10) == [0, 1, 2]
    assert parse_page_range("5", 10) == [4]
    assert parse_page_range("1-2,9-10", 10) == [0, 1, 8, 9]
    assert parse_page_range(None, 3) == [0, 1, 2]
