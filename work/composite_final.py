"""Final composites: 1 image per design per base photo. 5 designs x 2 bases = 10."""

import time
from pathlib import Path

from google import genai
from google.genai import types

WORK = Path(__file__).parent
PROJECT = "time-279118"
LOCATION = "global"
MODEL = "gemini-3-pro-image-preview"
VERSIONS = ["V1", "V2", "V3", "V5", "V6"]

BASES = {
    "studio": {
        "path": WORK / "bike_base3.jpg",
        "aspect": "3:2",
        "scene": 'a clean studio product shot on a seamless neutral gray backdrop with a soft gradient floor shadow. The bike is shown at a slight 3/4 angle from the drive side (right side), facing slightly toward the camera. It has drop handlebars with black bar tape, a black Ergon saddle, black seatpost, deep-section Zipp 303 carbon wheels with tan-sidewall Vittoria Corsa tires, a black drivetrain with silver chainrings, disc brake calipers, and two black water bottle cages on the frame. The current paint is solid yellow with small white "SCARAB" wordmarks.',
    },
    "alley": {
        "path": WORK / "bike_base_alley.jpg",
        "aspect": "3:2",
        "scene": 'an environmental shot in a tiled outdoor passageway. The bike is in pure left-side profile view (non-drive side), centered in the frame. Behind it is a worn white double-door with a padlock, flanked by red brick walls on both sides. The ground is tiled stone. The bike has black drop handlebars with bar tape, a black saddle, black seatpost, classic round-profile black wheels with black tires (no tan sidewalls, no deep section), a black rim brake drivetrain with silver crankset/chainrings visible, and a small "LETRAS" white panel on the down tube. The current paint is solid red.',
    },
}

PROMPT_TMPL = """You are editing a product photograph of a Scarab Cycles "Letras" road bicycle.

Image 1 is the source photograph: {scene}

Image 2 is a flat orthographic illustration of a custom paint scheme applied to the same Letras frame and fork. It shows exactly which paint colors and decorative artwork go on each tube: head tube, top tube, down tube, seat tube, seat stays, chain stays, and the fork legs.

Your task: produce a new photograph that is identical to Image 1 in every way EXCEPT the frame and fork are repainted to exactly match the paint scheme shown in Image 2.

Strict requirements:
- Keep the bike's geometry, pose, framing, camera angle, perspective, and scale identical to Image 1.
- Keep the entire background, floor, lighting, and shadows identical to Image 1.
- Keep all components unchanged and in exactly the same position: saddle, seatpost, handlebars and bar tape, stem, brake/shift levers, brake calipers, crankset and chainrings, derailleurs and chain, wheels, tires, water bottle cages, all cables and housings.
- Only the painted surfaces of the frame tubes and the fork legs change. Apply the colors, stripes, patterns, decals, logos ("SCARAB" wordmark, scarab beetle icon, "HECHO EN COLOMBIA" tag, Colombian flag stripe), and small decorative illustrations from Image 2 onto the corresponding tubes of the bike in Image 1. The base frame color must be the warm white shown in Image 2 (with the colored panels and decorations applied where the illustration shows them) — do not keep the original yellow or red paint.
- Wrap the artwork realistically around the cylindrical tubes with photographic lighting, subtle highlights and shadows on the curved metal surfaces, and a semi-matte clearcoat finish.
- Respect occlusion: where components, cables, or water bottle cages were in front of the frame in Image 1, they must still be in front of the frame in the output.
- Account for perspective and foreshortening of the frame in Image 1 when wrapping the artwork.
- Output a single photorealistic image at the same aspect ratio as Image 1. Do not add text overlays, borders, or watermarks."""


def load_image_part(path: Path) -> types.Part:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def main():
    client = genai.Client(vertexai=True, project=PROJECT, location=LOCATION)
    out_dir = WORK / "final"
    out_dir.mkdir(exist_ok=True)

    for base_name, base in BASES.items():
        bike_part = load_image_part(base["path"])
        prompt = PROMPT_TMPL.format(scene=base["scene"])
        for v in VERSIONS:
            design_part = load_image_part(WORK / f"frame_{v}_small.png")
            out_path = out_dir / f"{v}_{base_name}.png"
            if out_path.exists():
                print(f"skip {out_path.name}")
                continue
            print(f"generating {v} on {base_name} ...", flush=True)
            t0 = time.time()
            try:
                resp = client.models.generate_content(
                    model=MODEL,
                    contents=[prompt, bike_part, design_part],
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        candidate_count=1,
                        image_config=types.ImageConfig(
                            aspect_ratio=base["aspect"], image_size="2K"
                        ),
                    ),
                )
            except Exception as e:
                print(f"  ERROR: {e}", flush=True)
                continue
            saved = False
            for cand in resp.candidates or []:
                for part in cand.content.parts if cand.content else []:
                    if getattr(part, "inline_data", None) and part.inline_data.data:
                        out_path.write_bytes(part.inline_data.data)
                        saved = True
                        break
                if saved:
                    break
            dt = time.time() - t0
            print(
                f"  -> {out_path.name} ({out_path.stat().st_size // 1024} KB, {dt:.1f}s)"
                if saved
                else f"  no image ({dt:.1f}s)"
            )


if __name__ == "__main__":
    main()
