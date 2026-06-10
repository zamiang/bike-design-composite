"""Generate a photorealistic composite of a design onto a bike base photo."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from google import genai
from google.genai import types

MODEL = "gemini-3-pro-image-preview"


@dataclass
class Base:
    name: str
    label: str
    path: Path
    aspect: str
    scene: str


BIKES_DIR = Path(__file__).parent / "static" / "bikes"

BASES: dict[str, Base] = {
    "studio": Base(
        name="studio",
        label="Studio (gray backdrop, 3/4 drive side)",
        path=BIKES_DIR / "studio.jpg",
        aspect="3:2",
        scene=(
            "a clean studio product shot on a seamless neutral gray backdrop with a soft "
            "gradient floor shadow. The bike is shown at a slight 3/4 angle from the drive "
            "side (right side), facing slightly toward the camera. It has drop handlebars "
            "with black bar tape, a black Ergon saddle, black seatpost, deep-section Zipp 303 "
            "carbon wheels with Vittoria Corsa tires, a black drivetrain with "
            "silver chainrings, disc brake calipers, and two black water bottle cages on the "
            'frame. The current paint is solid yellow with small white "SCARAB" wordmarks.'
        ),
    ),
    "alley": Base(
        name="alley",
        label="Alley (tiled passageway, non-drive side)",
        path=BIKES_DIR / "alley.jpg",
        aspect="3:2",
        scene=(
            "an environmental shot in a tiled outdoor passageway. The bike is in pure "
            "left-side profile view (non-drive side), centered in the frame. Behind it is a "
            "worn white double-door with a padlock, flanked by red brick walls on both sides. "
            "The ground is tiled stone. The bike has black drop handlebars with bar tape, a "
            "black saddle, black seatpost, classic round-profile black wheels with black tires "
            "(no tan sidewalls, no deep section), a black rim brake drivetrain with silver "
            'crankset/chainrings visible, and a small "LETRAS" white panel on the down tube. '
            "The current paint is solid red."
        ),
    ),
    "chiva": Base(
        name="chiva",
        label="Chiva (yellow mural wall, drive side)",
        path=BIKES_DIR / "chiva.jpg",
        aspect="1:1",
        scene=(
            "an environmental shot against a hand-painted yellow wall reading "
            '"The Nonsense of Cycling" in black brush lettering, with a bare concrete '
            "block wall on the right and a smooth concrete floor. The bike is in near-full "
            "drive-side profile (right side), centered and facing right, with the drivetrain "
            "toward the camera. It has black drop handlebars with bar tape, a black saddle, a "
            "white seatpost, deep-section carbon wheels, a black disc "
            "brake drivetrain with silver chainrings, and visible disc rotors. The current "
            "paint is a warm white frame covered in a colorful patterned decal scheme."
        ),
    ),
}

PROMPT_TMPL = """You are editing a product photograph of a Scarab Cycles "Letras" road bicycle.

Image 1 is the source photograph: {scene}

Image 2 is a flat orthographic illustration of a custom paint scheme applied to the same Letras frame and fork. It shows exactly which paint colors and decorative artwork go on each tube: head tube, top tube, down tube, seat tube, seat stays, chain stays, and the fork legs.

Your task: produce a new photograph that is identical to Image 1 in every way EXCEPT the frame and fork are repainted to exactly match the paint scheme shown in Image 2.

Strict requirements:
- Keep the bike's geometry, pose, framing, camera angle, perspective, and scale identical to Image 1.
- Keep the entire background, floor, lighting, and shadows identical to Image 1.
- Keep these components unchanged and in exactly the same position: saddle, handlebars and bar tape, wheel rims and hubs, water bottle cages, all cables and housings.
- Apply the painted paint scheme from Image 2 to the frame tubes and the fork legs. Apply the colors, stripes, patterns, decals, logos ("SCARAB" wordmark, scarab beetle icon, "HECHO EN COLOMBIA" tag, Colombian flag stripe), and small decorative illustrations from Image 2 onto the corresponding tubes of the bike in Image 1. The base frame color must be the warm white shown in Image 2 (with the colored panels and decorations applied where the illustration shows them) — do not keep the original yellow or red paint.
- Change the following components on the bike (these are deliberate modifications, not preserved from Image 1):
  - Drivetrain and brakes: replace the existing groupset with a Shimano Dura-Ace 12-speed groupset — Dura-Ace shift/brake levers, front and rear derailleurs, crankset and chainrings, chain, and a 12-speed Dura-Ace cassette. Keep them in the same positions and mounting points, just rendered as Dura-Ace components.
  - Tires: replace the tires with wider 50mm tires mounted on the existing rims, keeping the wheels in the same position. The tires must be solid black with black sidewalls (no tan, gum, or brown sidewalls of any kind).
  - Stem and seatpost: paint the stem and the seatpost gloss white.
- Wrap the artwork realistically around the cylindrical tubes with photographic lighting, subtle highlights and shadows on the curved metal surfaces, and a semi-matte clearcoat finish.
- Respect occlusion: where components, cables, or water bottle cages were in front of the frame in Image 1, they must still be in front of the frame in the output.
- Account for perspective and foreshortening of the frame in Image 1 when wrapping the artwork.
- Output a single photorealistic image at the same aspect ratio as Image 1. Do not add text overlays, borders, or watermarks."""


def _part_from_path(path: Path) -> types.Part:
    mime = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime)


def _part_from_bytes(data: bytes, mime: str = "image/png") -> types.Part:
    return types.Part.from_bytes(data=data, mime_type=mime)


def composite(
    *,
    client: genai.Client,
    base: Base,
    design_png: bytes,
) -> bytes:
    resp = client.models.generate_content(
        model=MODEL,
        contents=[
            PROMPT_TMPL.format(scene=base.scene),
            _part_from_path(base.path),
            _part_from_bytes(design_png, "image/png"),
        ],
        config=types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            candidate_count=1,
            image_config=types.ImageConfig(aspect_ratio=base.aspect, image_size="2K"),
        ),
    )
    for cand in resp.candidates or []:
        for part in cand.content.parts if cand.content else []:
            if getattr(part, "inline_data", None) and part.inline_data.data:
                return part.inline_data.data
    raise RuntimeError("Model returned no image")
