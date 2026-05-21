"""Render a Scarab paint-spec PDF and crop the side-view frame illustration."""
from __future__ import annotations
import io
from pathlib import Path
import pypdfium2 as pdfium
from PIL import Image

# Crop bounds tuned for Scarab paint-spec layout at scale=0.5
# (PDF page is 5400x4209 pt; 0.5 -> 2700x2105; side-view sits at these bounds)
CROP = (990, 580, 2660, 1990)
RENDER_SCALE = 0.5


def render_first_page(pdf_bytes: bytes, scale: float = RENDER_SCALE) -> Image.Image:
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        page = pdf[0]
        pil = page.render(scale=scale).to_pil().convert("RGBA")
    finally:
        pdf.close()
    return pil


def knock_out_white(img: Image.Image, thresh: int = 252) -> Image.Image:
    img = img.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, _ = px[x, y]
            if r >= thresh and g >= thresh and b >= thresh:
                px[x, y] = (255, 255, 255, 0)
    return img


def extract_design(pdf_bytes: bytes) -> Image.Image:
    page = render_first_page(pdf_bytes)
    cropped = page.crop(CROP)
    return knock_out_white(cropped)


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1])
    out = src.with_suffix(".cropped.png")
    img = extract_design(src.read_bytes())
    out.write_bytes(to_png_bytes(img))
    print(f"wrote {out} ({img.size})")
