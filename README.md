# bike-design-composite

Composite a custom paint design onto a real photo of a bike, using Gemini 3 Pro Image (Nano Banana Pro) via Vertex AI.

Built for previewing Scarab Cycles custom paint specs on the actual Letras bike — see what the finished bike will look like before approving the build.

## What it does

Given:
- A flat orthographic illustration of a paint scheme (e.g. exported from a Scarab paint-spec PDF), and
- A photo of the bike to "paint"

…this pipeline produces a photorealistic image of the bike repainted with that design — preserving geometry, components, lighting, and background.

## Pipeline

1. **`work/extract.py`** — renders a Scarab paint-spec PDF to PNG (`pdftoppm`) and crops the side-view frame illustration. White page background is knocked out to alpha.
2. **`work/composite_final.py`** — calls Vertex AI's `gemini-3-pro-image-preview` with the source bike photo + the extracted design as two reference images, plus a strict prompt instructing the model to repaint only the frame tubes and fork.
3. **`Preview.html`** — local viewer to compare designs side by side.

## Requirements

- Python 3.10+
- `pip install google-genai pillow`
- `pdftoppm` (from poppler — `brew install poppler` on macOS)
- A GCP project with Vertex AI (`aiplatform.googleapis.com`) enabled
- `gcloud auth application-default login` (ADC)

## Running

```bash
# 1. Render and crop your paint-spec PDFs
python3 work/extract.py

# 2. Generate composites against the base photo(s)
python3 work/composite_final.py
```

Edit `PROJECT`, `VERSIONS`, and `BASES` at the top of `composite_final.py` for your setup.

## Cost

About **$0.15 per generated image** (`gemini-3-pro-image-preview`, 2K output, ~30–60 s per image).

## Web app

See [`web/`](web/) for a password-protected FastAPI app that wraps this pipeline — upload a paint-spec PDF, pick which bundled bike photos to composite onto, get the results back. Deployable to Cloud Run; see `web/README.md`.

## Status

Started as a single-shot preview for one specific frame design (Scarab Letras 26035). The `web/` app generalizes it so anyone ordering a custom Scarab can preview their paint before pulling the trigger.
