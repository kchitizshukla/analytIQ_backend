"""Authentication tests — password hashing, session tokens, and login API.

The API tests exercise the seeded demo account (read-only: no rows are created
or mutated) so they are safe to run against the development database.
"""
import time
import uuid

from fastapi.testclient import TestClient

from app.core import security
from app.main import app

client = TestClient(app)

DEMO_EMAIL = "demo@analytiq.local"
DEMO_PASSWORD = "AnalytIQ@123"


def _login() -> TestClient:
    c = TestClient(app)
    assert c.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}).status_code == 200
    return c


# ----------------------------- password hashing ----------------------------- #
def test_hash_and_verify_roundtrip():
    h = security.hash_password("S3cretPass")
    assert h != "S3cretPass"  # never plaintext
    assert h.startswith("$2")  # bcrypt
    assert security.verify_password("S3cretPass", h) is True
    assert security.verify_password("wrong", h) is False


def test_verify_handles_missing_or_malformed_hash():
    assert security.verify_password("x", None) is False
    assert security.verify_password("x", "not-a-bcrypt-hash") is False


# ------------------------------ session tokens ------------------------------ #
def test_session_token_roundtrip():
    uid = uuid.uuid4()
    token = security.create_session_token(uid)
    assert security.read_session_token(token) == uid


def test_session_token_rejects_tampering():
    token = security.create_session_token(uuid.uuid4())
    body, _, sig = token.partition(".")
    forged = body + "." + ("a" if sig[0] != "a" else "b") + sig[1:]
    assert security.read_session_token(forged) is None
    assert security.read_session_token(None) is None
    assert security.read_session_token("garbage") is None


def test_session_token_expiry():
    token = security.create_session_token(uuid.uuid4(), ttl_hours=0)
    time.sleep(1)
    assert security.read_session_token(token) is None


# -------------------------------- login API --------------------------------- #
def test_login_wrong_password_rejected():
    r = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": "wrongpassword"})
    assert r.status_code == 401
    assert r.json()["detail"]["code"] == "INVALID_CREDENTIALS"


def test_login_unknown_email_rejected():
    r = client.post("/api/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert r.status_code == 401


def test_login_invalid_email_format():
    r = client.post("/api/auth/login", json={"email": "not-an-email", "password": "x"})
    assert r.status_code == 422


def test_login_demo_success_sets_cookie_and_hides_secrets():
    r = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    assert r.status_code == 200
    assert security.settings.session_cookie_name in r.cookies
    body = r.json()["user"]
    assert body["email"] == DEMO_EMAIL
    assert "password" not in body and "password_hash" not in body


def test_me_requires_authentication():
    # Fresh client so no persisted cookie from a prior login leaks in.
    with TestClient(app) as fresh:
        fresh.cookies.clear()
        assert fresh.get("/api/auth/me").status_code == 401


def test_me_returns_user_with_valid_session():
    login = client.post("/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD})
    cookie = login.cookies.get(security.settings.session_cookie_name)
    r = client.get("/api/auth/me", cookies={security.settings.session_cookie_name: cookie})
    assert r.status_code == 200
    assert r.json()["email"] == DEMO_EMAIL


def test_signup_duplicate_email_conflict():
    r = client.post(
        "/api/auth/signup",
        json={"name": "Dupe", "email": DEMO_EMAIL, "password": "Abcd1234"},
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "EMAIL_EXISTS"


def test_change_password_requires_auth():
    with TestClient(app) as fresh:
        fresh.cookies.clear()
        r = fresh.post("/api/auth/change-password",
                       json={"current_password": "x", "new_password": "Abcd1234"})
        assert r.status_code == 401


def test_change_password_wrong_current_rejected():
    c = _login()
    r = c.post("/api/auth/change-password",
               json={"current_password": "wrong-pass", "new_password": "Abcd1234"})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "INVALID_CURRENT_PASSWORD"


def test_change_password_roundtrip_and_revert():
    c = _login()
    # change to a temporary password
    r = c.post("/api/auth/change-password",
               json={"current_password": DEMO_PASSWORD, "new_password": "TempPass9"})
    assert r.status_code == 200
    try:
        # old password no longer works, new one does
        assert TestClient(app).post(
            "/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
        ).status_code == 401
        assert TestClient(app).post(
            "/api/auth/login", json={"email": DEMO_EMAIL, "password": "TempPass9"}
        ).status_code == 200
    finally:
        # revert so the demo account is unchanged for other tests / demos
        c.post("/api/auth/change-password",
               json={"current_password": "TempPass9", "new_password": DEMO_PASSWORD})
    assert TestClient(app).post(
        "/api/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD}
    ).status_code == 200


def test_signup_weak_password_rejected():
    r = client.post(
        "/api/auth/signup",
        json={"name": "Weak", "email": "weak-" + uuid.uuid4().hex + "@example.com", "password": "short"},
    )
    assert r.status_code == 422
