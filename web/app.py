"""Small password-protected web app: upload a Scarab paint-spec PDF, get composites back."""

from __future__ import annotations

import base64
import os
import secrets
import time
import uuid
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

APP_PASSWORD = os.environ.get("APP_PASSWORD")
SESSION_SECRET = os.environ.get("SESSION_SECRET") or secrets.token_urlsafe(32)
GCP_PROJECT = os.environ.get("GCP_PROJECT", "time-279118")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "global")
COOKIE_NAME = "bd_session"

if not APP_PASSWORD:
    # Fail loudly on startup rather than silently allowing entry.
    raise RuntimeError("APP_PASSWORD env var is required")

signer = URLSafeSerializer(SESSION_SECRET, salt="bd-auth")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
genai_client = genai.Client(vertexai=True, project=GCP_PROJECT, location=GCP_LOCATION)

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


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
    return templates.TemplateResponse("login.html", {"request": request, "error": error})


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
        "index.html",
        {"request": request, "bases": list(BASES.values())},
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
    with ThreadPoolExecutor(max_workers=len(chosen)) as ex:
        futures = [ex.submit(run_one, b) for b in chosen]
        for base, fut in zip(chosen, futures, strict=True):
            try:
                _, img_bytes = fut.result()
                results.append((base, base64.b64encode(img_bytes).decode("ascii")))
            except Exception as e:
                errors.append((base, str(e)))

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "job_id": job_id,
            "elapsed": f"{time.time() - t0:.1f}",
            "design_b64": base64.b64encode(design_png).decode("ascii"),
            "results": results,
            "errors": errors,
            "pdf_name": pdf.filename,
        },
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}
