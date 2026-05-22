"""Shared test fixtures.

The app imports `google.genai` and constructs a Vertex client at module import
time. Tests stub that out so importing `app` doesn't require GCP credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

WEB_DIR = Path(__file__).resolve().parent.parent
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))


@pytest.fixture()
def app_module(monkeypatch):
    os.environ.setdefault("APP_PASSWORD", "test-password")
    os.environ.setdefault("SESSION_SECRET", "test-secret-do-not-use-in-prod")

    fake_genai = MagicMock()
    fake_genai.Client.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    sys.modules.pop("app", None)
    import app  # noqa: PLC0415

    return app
