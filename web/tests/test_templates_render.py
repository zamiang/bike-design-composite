"""Regression tests for TemplateResponse calls.

Starlette removed the legacy `TemplateResponse(name, context)` signature; the
current API is `TemplateResponse(request, name, context)`. Calling the old
form with a recent Starlette raises `TypeError: unhashable type: 'dict'` at
runtime (the context dict gets treated as the template name and Jinja tries
to hash it as a cache key). These tests render every template-returning
route so a regression fails CI instead of production.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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
