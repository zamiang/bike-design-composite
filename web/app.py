"""Small password-protected web app: upload a Scarab paint-spec PDF, get composites back."""

from __future__ import annotations

import io
import logging
import os
import re
import secrets
import threading
import time
import uuid
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from composite import BASES, composite
from extract import extract_design, to_png_bytes
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from google import genai
from itsdangerous import BadSignature, URLSafeSerializer
from PIL import Image

APP_PASSWORD = os.environ.get("APP_PASSWORD")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(32)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "time-279118")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "global")
RESULTS_BUCKET = os.environ.get("RESULTS_BUCKET")
COOKIE_NAME = "bd_session"

logger = logging.getLogger(__name__)

if not APP_PASSWORD:
    # Fail loudly on startup rather than silently allowing entry.
    raise RuntimeError("APP_PASSWORD env var is required")

signer = URLSafeSerializer(SESSION_SECRET, salt="bd-auth")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
genai_client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

# Composites are inlined into the response page as URLs pointing back at this
# app, which keeps any single HTTP response well under Cloud Run's 32 MiB cap
# (it used to base64-inline ~5 MB per composite, which blew past the limit with
# multiple frames).
#
# Those follow-up image GETs to /result/{job_id}/... are load-balanced across
# instances, so the results have to live somewhere every instance can reach:
# the GCS bucket named by RESULTS_BUCKET. (Before this, results lived only in
# the instance that ran /generate; any GET routed elsewhere, common under
# autoscaling, 404'd.) The bucket has a lifecycle rule that expires objects, so
# there's nothing to prune in-process.
#
# When RESULTS_BUCKET is unset (local dev, tests) we fall back to an in-process
# store so the app runs without GCP. That store isn't shared across instances,
# which is fine for single-process local use.
_RESULTS_LOCK = threading.Lock()
_RESULTS: OrderedDict[str, dict] = OrderedDict()
_RESULTS_MAX_JOBS = 20
_RESULTS_TTL_SEC = 60 * 60  # 1 hour
_JOB_ID_RE = re.compile(r"^[0-9a-f]{8}$")
_ASSET_NAME_RE = re.compile(r"^[a-z0-9_-]{1,40}$")

# Lazily built so importing this module (e.g. in tests) needs no GCP creds, and
# so the in-memory fallback path never touches google-cloud-storage.
_storage_lock = threading.Lock()
_storage_client = None


def _results_bucket():
    global _storage_client
    if _storage_client is None:
        with _storage_lock:
            if _storage_client is None:
                from google.cloud import storage  # noqa: PLC0415

                _storage_client = storage.Client(project=GCP_PROJECT)
    return _storage_client.bucket(RESULTS_BUCKET)


def _prune_results() -> None:
    now = time.time()
    expired = [k for k, v in _RESULTS.items() if now - v["created"] > _RESULTS_TTL_SEC]
    for k in expired:
        _RESULTS.pop(k, None)
    while len(_RESULTS) > _RESULTS_MAX_JOBS:
        _RESULTS.popitem(last=False)


def _store_job(job_id: str, assets: dict[str, bytes]) -> set[str]:
    """Persist a job's assets. Returns the set of asset names that failed to
    store (empty on full success). A single failed upload must not throw away
    the composites that did store, nor 500 the whole /generate response, so the
    GCS path uploads each asset independently and reports the failures."""
    if not RESULTS_BUCKET:
        with _RESULTS_LOCK:
            _RESULTS[job_id] = {"created": time.time(), "assets": assets}
            _RESULTS.move_to_end(job_id)
            _prune_results()
        return set()
    bucket = _results_bucket()
    failed = set()
    for name, data in assets.items():
        try:
            bucket.blob(f"{job_id}/{name}").upload_from_string(data)
        except Exception:
            logger.exception("failed to store result asset %s/%s", job_id, name)
            failed.add(name)
    return failed


def _get_asset(job_id: str, name: str) -> bytes | None:
    if not RESULTS_BUCKET:
        with _RESULTS_LOCK:
            job = _RESULTS.get(job_id)
            return job["assets"].get(name) if job else None
    from google.cloud.exceptions import NotFound  # noqa: PLC0415

    try:
        return _results_bucket().blob(f"{job_id}/{name}").download_as_bytes()
    except NotFound:
        return None
    except Exception:
        # Transient GCS trouble (auth drift, 503, network) shouldn't 500 the
        # image GET and break the whole result page; log it and let the caller
        # render a missing asset so the user can re-render.
        logger.exception("failed to fetch result asset %s/%s", job_id, name)
        return None


def _to_jpeg(png_bytes: bytes, quality: int = 88) -> bytes:
    """Re-encode a PNG to JPEG. Cuts composite size ~5-10x at visually negligible loss."""
    with Image.open(io.BytesIO(png_bytes)) as im:
        if im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, format="JPEG", quality=quality, optimize=True, progressive=True)
        return out.getvalue()


def require_auth(request: Request) -> None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="login required")
    try:
        if signer.loads(token) != "ok":
            raise HTTPException(status_code=401, detail="login required")
    except BadSignature as e:
        raise HTTPException(status_code=401, detail="login required") from e


@app.exception_handler(HTTPException)
async def auth_redirect(request: Request, exc: HTTPException):
    if exc.status_code == 401:
        return RedirectResponse("/login", status_code=303)
    return Response(content=exc.detail, status_code=exc.status_code)


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request, error: str | None = None):
    return templates.TemplateResponse(request, "login.html", {"error": error})


@app.post("/login")
def login_submit(password: str = Form(...)):
    if not secrets.compare_digest(password, APP_PASSWORD):
        return RedirectResponse("/login?error=1", status_code=303)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(
        COOKIE_NAME,
        signer.dumps("ok"),
        httponly=True,
        secure=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    return resp


@app.post("/logout")
def logout():
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/", response_class=HTMLResponse)
def index(request: Request, _: None = Depends(require_auth)):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"bases": list(BASES.values())},
    )


@app.post("/generate", response_class=HTMLResponse)
async def generate(
    request: Request,
    pdf: UploadFile = File(...),
    bases: list[str] = Form(...),
    _: None = Depends(require_auth),
):
    # Stream the upload so a 1 GB PDF can't fill the container before we reject it.
    # Cap at 50 MB; with concurrency=4, that bounds in-flight upload memory to ~200 MB.
    max_bytes = 50 * 1024 * 1024
    chunk_size = 1024 * 1024
    buf = bytearray()
    while chunk := await pdf.read(chunk_size):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HTTPException(status_code=413, detail="file too large (50 MB max)")
    if not buf:
        raise HTTPException(status_code=400, detail="empty file")
    pdf_bytes = bytes(buf)

    chosen = [BASES[b] for b in bases if b in BASES]
    if not chosen:
        raise HTTPException(status_code=400, detail="pick at least one bike photo")

    job_id = uuid.uuid4().hex[:8]
    t0 = time.time()

    design_img = extract_design(pdf_bytes)
    design_png = to_png_bytes(design_img)

    def run_one(base):
        return base, composite(client=genai_client, base=base, design_png=design_png)

    results = []
    errors = []
    assets: dict[str, bytes] = {"design": design_png}
    with ThreadPoolExecutor(max_workers=len(chosen)) as ex:
        futures = [ex.submit(run_one, b) for b in chosen]
        for base, fut in zip(chosen, futures, strict=True):
            try:
                _, img_bytes = fut.result()
                assets[base.name] = _to_jpeg(img_bytes)
                results.append(base)
            except Exception as e:
                errors.append((base, str(e)))

    store_failures = _store_job(job_id, assets)
    if store_failures:
        # A composite that rendered but couldn't be persisted would link a
        # broken image; surface it as an error instead and drop it from results.
        for base in results:
            if base.name in store_failures:
                errors.append((base, "result could not be saved, please re-render"))
        results = [base for base in results if base.name not in store_failures]

    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "job_id": job_id,
            "elapsed": f"{time.time() - t0:.1f}",
            "results": results,
            "errors": errors,
            "pdf_name": pdf.filename,
        },
    )


@app.get("/result/{job_id}/{name}.{ext}")
def result_asset(job_id: str, name: str, ext: str, _: None = Depends(require_auth)):
    if not _JOB_ID_RE.match(job_id) or not _ASSET_NAME_RE.match(name) or ext not in ("jpg", "png"):
        raise HTTPException(status_code=404, detail="not found")
    data = _get_asset(job_id, name)
    if data is None:
        raise HTTPException(status_code=404, detail="not found")
    # The template only ever links each asset with its real extension (composites
    # as .jpg, the extracted design as .png), so the ext maps 1:1 to the mime.
    mime = "image/png" if ext == "png" else "image/jpeg"
    return Response(
        content=data,
        media_type=mime,
        headers={"Cache-Control": "private, max-age=3600"},
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}
