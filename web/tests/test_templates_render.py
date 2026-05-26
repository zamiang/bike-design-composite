"""Regression tests for TemplateResponse calls.

Starlette removed the legacy `TemplateResponse(name, context)` signature; the
current API is `TemplateResponse(request, name, context)`. Calling the old
form with a recent Starlette raises `TypeError: unhashable type: 'dict'` at
runtime (the context dict gets treated as the template name and Jinja tries
to hash it as a cache key). These tests render every template-returning
route so a regression fails CI instead of production.
"""

from __future__ import annotations

import io

from fastapi.testclient import TestClient
from PIL import Image


def _tiny_png() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (4, 4), (200, 120, 90)).save(out, format="PNG")
    return out.getvalue()


def _client(app_module, *, authenticated: bool = False):
    client = TestClient(app_module.app, follow_redirects=False)
    if authenticated:
        client.cookies.set(app_module.COOKIE_NAME, app_module.signer.dumps("ok"))
    return client


def test_login_page_renders(app_module):
    response = _client(app_module).get("/login")
    assert response.status_code == 200
    assert "<form" in response.text.lower()


def test_login_page_renders_with_error_param(app_module):
    response = _client(app_module).get("/login?error=bad")
    assert response.status_code == 200


def test_index_renders_when_authenticated(app_module):
    response = _client(app_module, authenticated=True).get("/")
    assert response.status_code == 200


def test_index_redirects_when_unauthenticated(app_module):
    response = _client(app_module).get("/")
    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_generate_renders_result(app_module, monkeypatch):
    """The /generate response renders result.html (the third TemplateResponse
    call site). Stub the PDF extraction and Vertex composite so the route
    exercises only request handling and the template render, not GCP."""
    png = _tiny_png()
    monkeypatch.setattr(app_module, "extract_design", lambda pdf_bytes: object())
    monkeypatch.setattr(app_module, "to_png_bytes", lambda img: png)
    monkeypatch.setattr(app_module, "composite", lambda **kwargs: png)

    response = _client(app_module, authenticated=True).post(
        "/generate",
        files={"pdf": ("spec.pdf", b"%PDF-1.4 stub", "application/pdf")},
        data={"bases": "studio"},
    )
    assert response.status_code == 200
    # Confirms result.html (not index) rendered with our context.
    assert "spec.pdf" in response.text
    assert "/result/" in response.text
