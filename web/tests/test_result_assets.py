"""Result asset serving: the /generate response links each composite back at
/result/{job_id}/{name}.{ext}, and those GETs must round-trip the stored bytes.

These exercise the in-memory fallback store (RESULTS_BUCKET unset). In
production the same _store_job/_get_asset pair is backed by GCS so the asset
GETs resolve no matter which Cloud Run instance serves them; the regression we
care about here is that the store/route contract holds at all.
"""

from __future__ import annotations

import io
import re

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


def _generate(app_module, monkeypatch, bases: str = "studio"):
    png = _tiny_png()
    monkeypatch.setattr(app_module, "extract_design", lambda pdf_bytes: object())
    monkeypatch.setattr(app_module, "to_png_bytes", lambda img: png)
    monkeypatch.setattr(app_module, "composite", lambda **kwargs: png)
    client = _client(app_module, authenticated=True)
    response = client.post(
        "/generate",
        files={"pdf": ("spec.pdf", b"%PDF-1.4 stub", "application/pdf")},
        data={"bases": bases},
    )
    assert response.status_code == 200
    return client, response


def test_result_assets_round_trip(app_module, monkeypatch):
    client, response = _generate(app_module, monkeypatch)
    # Pull every /result/ URL the template rendered and fetch each one.
    urls = set(re.findall(r"/result/[0-9a-f]{8}/[a-z0-9_-]+\.(?:jpg|png)", response.text))
    assert any(u.endswith("/studio.jpg") for u in urls)
    assert any(u.endswith("/design.png") for u in urls)
    for url in urls:
        asset = client.get(url)
        assert asset.status_code == 200, url
        assert asset.content
        expected = "image/png" if url.endswith(".png") else "image/jpeg"
        assert asset.headers["content-type"] == expected


def test_result_asset_unknown_job_404(app_module):
    response = _client(app_module, authenticated=True).get("/result/deadbeef/studio.jpg")
    assert response.status_code == 404


def test_result_asset_requires_auth(app_module, monkeypatch):
    _, response = _generate(app_module, monkeypatch)
    url = re.search(r"/result/[0-9a-f]{8}/studio\.jpg", response.text).group(0)
    # A fresh, unauthenticated client must not be able to fetch the asset.
    unauth = _client(app_module).get(url)
    assert unauth.status_code in (303, 401, 403)


class _FakeBlob:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def upload_from_string(self, data):
        self._store[self._key] = data

    def download_as_bytes(self):
        from google.cloud.exceptions import NotFound  # noqa: PLC0415

        if self._key not in self._store:
            raise NotFound(self._key)
        return self._store[self._key]


class _FakeBucket:
    def __init__(self, store):
        self._store = store

    def blob(self, key):
        return _FakeBlob(self._store, key)


def test_gcs_backed_store_round_trips_and_keys_by_job(app_module, monkeypatch):
    """Exercise the production (RESULTS_BUCKET set) branch with a fake bucket:
    assets key as {job_id}/{name}, round-trip, and a miss returns None (-> 404)."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(app_module, "RESULTS_BUCKET", "fake-bucket")
    monkeypatch.setattr(app_module, "_results_bucket", lambda: _FakeBucket(store))

    assert app_module._store_job("abcd1234", {"design": b"PNG", "studio": b"JPEG"}) == set()
    assert store == {"abcd1234/design": b"PNG", "abcd1234/studio": b"JPEG"}
    assert app_module._get_asset("abcd1234", "studio") == b"JPEG"
    assert app_module._get_asset("abcd1234", "design") == b"PNG"
    assert app_module._get_asset("abcd1234", "missing") is None
    assert app_module._get_asset("00000000", "studio") is None


class _FlakyBucket:
    """Uploads of `failing_key` raise; everything else stores. Reads of a stored
    key succeed, and a transient (non-NotFound) read error surfaces too."""

    def __init__(self, store, *, failing_key):
        self._store = store
        self._failing_key = failing_key

    def blob(self, key):
        if key == self._failing_key:
            return _RaisingBlob(key)
        return _FakeBlob(self._store, key)


class _RaisingBlob:
    def __init__(self, key):
        self._key = key

    def upload_from_string(self, data):
        raise RuntimeError(f"GCS unavailable for {self._key}")

    def download_as_bytes(self):
        raise RuntimeError(f"GCS unavailable for {self._key}")


def test_store_job_reports_failed_assets_without_dropping_the_rest(app_module, monkeypatch):
    """A single failed upload is reported (not raised) and the assets that did
    store are still persisted, so /generate can degrade instead of 500-ing."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(app_module, "RESULTS_BUCKET", "fake-bucket")
    monkeypatch.setattr(
        app_module, "_results_bucket", lambda: _FlakyBucket(store, failing_key="abcd1234/studio")
    )

    failed = app_module._store_job("abcd1234", {"design": b"PNG", "studio": b"JPEG"})
    assert failed == {"studio"}
    assert store == {"abcd1234/design": b"PNG"}  # the good asset still landed


def test_get_asset_transient_error_returns_none(app_module, monkeypatch):
    """A non-NotFound GCS read error degrades to None (-> 404) instead of 500."""
    store: dict[str, bytes] = {}
    monkeypatch.setattr(app_module, "RESULTS_BUCKET", "fake-bucket")
    monkeypatch.setattr(
        app_module, "_results_bucket", lambda: _FlakyBucket(store, failing_key="abcd1234/studio")
    )

    assert app_module._get_asset("abcd1234", "studio") is None
