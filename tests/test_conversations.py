"""AnalytIQ Assistant conversation tests — CRUD, auth, ownership, titles.

The CRUD test is self-cleaning (it deletes the conversation it creates) so it is
safe to run against the development database.
"""
import uuid

from fastapi.testclient import TestClient

from app.ai import analyst
from app.main import app

client = TestClient(app)

DEMO_EMAIL = "demo@analytiq.local"
DEMO_PASSWORD = "AnalytIQ@123"
DEMO_DATASET_ID = "a1b2c3d4-0000-4000-8000-000000000001"


def _login() -> TestClient:
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    return c


# ------------------------------- title logic -------------------------------- #
def test_generate_title_is_concise_and_not_full_question():
    t = analyst.generate_title("What were the top 5 products by revenue?")
    assert 0 < len(t.split()) <= 6
    assert t.lower() != "what were the top 5 products by revenue?"
    assert "product" in t.lower()


def test_generate_title_handles_empty():
    assert analyst.generate_title("") == "New conversation"


# --------------------------------- auth ------------------------------------- #
def test_conversations_require_auth():
    assert TestClient(app).get("/api/assistant/conversations").status_code == 401


def test_get_unknown_conversation_404():
    c = _login()
    r = c.get(f"/api/assistant/conversations/{uuid.uuid4()}")
    assert r.status_code == 404


# ------------------------------- CRUD cycle --------------------------------- #
def test_conversation_crud_roundtrip():
    c = _login()
    # create
    r = c.post("/api/assistant/conversations", json={"dataset_id": DEMO_DATASET_ID, "title": "Test convo"})
    assert r.status_code == 201
    conv = r.json()
    cid = conv["id"]
    assert conv["dataset_name"]  # dataset name is resolved for the sidebar
    try:
        # appears in the user's list
        lst = c.get("/api/assistant/conversations").json()
        assert any(x["id"] == cid for x in lst)

        # rename
        r = c.patch(f"/api/assistant/conversations/{cid}", json={"title": "Renamed convo"})
        assert r.status_code == 200 and r.json()["title"] == "Renamed convo"

        # messages start empty
        msgs = c.get(f"/api/assistant/conversations/{cid}/messages")
        assert msgs.status_code == 200 and msgs.json() == []
    finally:
        # delete + confirm gone
        assert c.delete(f"/api/assistant/conversations/{cid}").status_code == 204
    assert c.get(f"/api/assistant/conversations/{cid}").status_code == 404
