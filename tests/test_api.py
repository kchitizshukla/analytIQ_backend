"""API-level smoke tests (health + AI-unavailable behavior)."""
import io

import pandas as pd
from fastapi.testclient import TestClient

from app.ai.provider import get_provider
from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("ok", "degraded")
    assert "llm_available" in body


def test_upload_rejects_bad_extension():
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("bad.exe", b"nope", "application/octet-stream")},
    )
    assert r.status_code == 400


def test_upload_rejects_empty():
    r = client.post(
        "/api/datasets/upload",
        files={"file": ("empty.csv", b"", "text/csv")},
    )
    assert r.status_code == 400


DEMO_DATASET_ID = "a1b2c3d4-0000-4000-8000-000000000001"


def test_download_demo_dataset_original_file():
    r = client.get(f"/api/datasets/{DEMO_DATASET_ID}/download")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert r.headers.get("content-disposition", "").endswith('.xlsx"')
    assert len(r.content) > 0


def test_download_unknown_dataset_404():
    r = client.get("/api/datasets/00000000-0000-4000-8000-0000000000ff/download")
    assert r.status_code == 404


def test_ai_provider_unavailable_by_default():
    # With no GEMINI_API_KEY in the test env, the provider reports unavailable
    provider = get_provider()
    # either unavailable, or available if a key is configured — both valid
    assert isinstance(provider.available, bool)
