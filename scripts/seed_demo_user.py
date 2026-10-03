"""Idempotently seed (or refresh) the AnalytIQ demo account.

Creates the demo user with a freshly computed bcrypt hash, or updates the
existing row's name/password so local/investor demos always work:

    Email:    demo@analytiq.local
    Password: AnalytIQ@123

The password is never stored in plaintext — only its salted bcrypt hash.

Run:  backend/.venv/bin/python -m scripts.seed_demo_user
"""
from __future__ import annotations

import uuid

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User
from app.repositories import user_repo

DEMO_USER_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")
DEMO_NAME = "AnalytIQ Demo User"
DEMO_EMAIL = "demo@analytiq.local"
DEMO_PASSWORD = "AnalytIQ@123"


def main() -> None:
    db = SessionLocal()
    try:
        user = user_repo.get_by_email(db, DEMO_EMAIL) or db.get(User, DEMO_USER_ID)
        pw_hash = hash_password(DEMO_PASSWORD)
        if user:
            user.name = DEMO_NAME
            user.email = DEMO_EMAIL
            user.password_hash = pw_hash
            action = "Updated"
        else:
            user = User(id=DEMO_USER_ID, name=DEMO_NAME, email=DEMO_EMAIL, password_hash=pw_hash)
            db.add(user)
            action = "Created"
        db.commit()
        print(f"{action} demo user: {DEMO_EMAIL}  (password: {DEMO_PASSWORD})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
