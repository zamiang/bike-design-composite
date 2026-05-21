from PIL import Image
import os

# The main side-view frame illustration sits roughly in the lower-right area
# of each page. Crop bounds determined from page_V1-1.png (2700x2105).
# These bounds are consistent across all 5 PDFs (same template).
SRC = "/Users/brennanmoore/Documents/Bike design/work"
# Crop box around the side-view frame illustration only (no headers, no swatches, no top/rear views)
# Tight bounds: x from ~860 to ~2680, y from ~470 to ~2010
CROP = (990, 580, 2660, 1990)

for v in ("V1", "V2", "V3", "V5", "V6"):
    img = Image.open(f"{SRC}/page_{v}-1.png").convert("RGBA")
    side = img.crop(CROP)
    # Make near-white pixels transparent so it overlays on the bike photo.
    # But the frame has "warm white" sections — preserve those by only knocking
    # out pure white (the page background).
    px = side.load()
    w, h = side.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            # Page background is pure #FFFFFF. Warm white frame has slight tint
            # but in the rendered raster it's still very close to white. We'll
            # threshold high so frame whites survive.
            if r >= 252 and g >= 252 and b >= 252:
                px[x, y] = (255, 255, 255, 0)
    side.save(f"{SRC}/frame_{v}.png", optimize=True)
    print(v, side.size)
