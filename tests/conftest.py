from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageDraw


@pytest.fixture()
def text_page_image() -> Image.Image:
    """Synthetic grayscale 'scanned page': dark line blocks on white."""
    img = Image.new("L", (800, 1200), 250)
    draw = ImageDraw.Draw(img)
    for y in range(150, 1050, 60):
        draw.rectangle([120, y, 680, y + 28], fill=30)
    return img


@pytest.fixture()
def tiny_pdf(tmp_path: Path) -> Path:
    Image.init()
    pages = []
    for i in range(3):
        img = Image.new("L", (800, 1200), 255)
        draw = ImageDraw.Draw(img)
        for y in range(150, 1050, 60):
            draw.rectangle([120, y, 680, y + 28], fill=30)
        draw.text((390, 40), str(i + 1), fill=0)
        pages.append(img)
    out = tmp_path / "sample.pdf"
    pages[0].save(out, save_all=True, append_images=pages[1:], resolution=150)
    return out
