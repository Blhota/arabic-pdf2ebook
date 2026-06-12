"""Wi-Fi upload to CrossPoint e-readers (Xteink X3/X4).

CrossPoint's built-in web server accepts `POST /upload` with a multipart
`file` field; the device announces itself as http://crosspoint.local
(see crosspoint-reader docs/webserver-endpoints.md).
"""

from __future__ import annotations

import json
import os
import urllib.request
import uuid
from pathlib import Path

DEFAULT_HOST = "crosspoint.local"
UPLOAD_TIMEOUT = 120


def _config_path() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".config")
    d = Path(base) / "pdf2ebook"
    d.mkdir(parents=True, exist_ok=True)
    return d / "config.json"


def load_config() -> dict:
    path = _config_path()
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(config: dict) -> None:
    _config_path().write_text(json.dumps(config, indent=2), encoding="utf-8")


def _multipart_body(field: str, filename: str, data: bytes,
                    content_type: str = "application/epub+zip") -> tuple[bytes, str]:
    boundary = f"----pdf2ebook{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8")
    tail = f"\r\n--{boundary}--\r\n".encode("utf-8")
    return head + data + tail, boundary


def resolve_host(host: str | None) -> str:
    config = load_config()
    host = (host or config.get("reader_host") or DEFAULT_HOST).strip()
    return host.removeprefix("http://").removeprefix("https://").strip("/")


def upload_file(path: Path, host: str | None = None, dest_path: str = "/",
                content_type: str = "application/octet-stream") -> str:
    """Upload any file to the CrossPoint reader; returns the host used."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    host = resolve_host(host)

    body, boundary = _multipart_body("file", path.name, path.read_bytes(), content_type)
    url = f"http://{host}/upload?path={urllib.parse.quote(dest_path)}"
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT) as response:  # noqa: S310
            if response.status != 200:
                raise RuntimeError(f"Reader answered HTTP {response.status}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"Could not reach the reader at '{host}'. "
            "On the reader, open Menu → File Transfer to turn on Wi-Fi mode — it shows an "
            "address like 192.168.1.50 on its screen; enter that address and try again. | "
            f"تعذر الوصول إلى القارئ على العنوان '{host}'. "
            "افتح على القارئ: القائمة ← نقل الملفات لتشغيل وضع Wi-Fi — سيظهر عنوان مثل "
            "192.168.1.50 على شاشته؛ اكتب ذلك العنوان وحاول مجددًا."
        ) from exc

    config = load_config()
    config["reader_host"] = host
    save_config(config)
    return host


def send_to_reader(epub: Path, host: str | None = None, dest_path: str = "/") -> str:
    """Upload an EPUB to the reader; returns the target host used."""
    return upload_file(epub, host, dest_path, content_type="application/epub+zip")
