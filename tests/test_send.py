from __future__ import annotations

import io
import urllib.error
import urllib.request

import pytest

from pdf2ebook import send


def _http_error(code: int, body: bytes = b"Failed to create file on SD card"):
    return urllib.error.HTTPError(
        url="http://reader/upload", code=code, msg="Bad Request",
        hdrs=None, fp=io.BytesIO(body),
    )


def test_upload_reports_reader_refusal_not_network(tmp_path, monkeypatch):
    """HTTP 400 from the reader must NOT be reported as 'could not reach'."""
    f = tmp_path / "x.epub"
    f.write_bytes(b"data")

    def fake_urlopen(request, timeout=0):
        raise _http_error(400)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(send, "save_config", lambda c: None)
    with pytest.raises(RuntimeError) as exc:
        send.upload_file(f, host="192.168.1.50")
    msg = str(exc.value)
    assert "HTTP 400" in msg and "SD card" in msg
    assert "Could not reach" not in msg


def test_upload_unreachable_gives_bilingual_hint(tmp_path, monkeypatch):
    f = tmp_path / "x.epub"
    f.write_bytes(b"data")

    def fake_urlopen(request, timeout=0):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as exc:
        send.upload_file(f, host="nope.local")
    msg = str(exc.value)
    assert "Could not reach" in msg and "نقل الملفات" in msg


def test_mkdir_tolerates_existing_folder(monkeypatch):
    def fake_urlopen(request, timeout=0):
        raise _http_error(400, b"exists")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert send.mkdir_on_reader(".fonts", host="192.168.1.50") is False  # no exception
