"""Data-access layer for users. All DB logic lives here, not in routes."""
from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User


def get_by_email(db: Session, email: str) -> User | None:
    # Case-insensitive lookup so logins aren't tripped up by capitalisation.
    return db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))


def get_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.scalar(select(User).where(User.id == user_id))


def create_user(db: Session, *, name: str, email: str, password_hash: str) -> User:
    user = User(name=name.strip(), email=email.strip().lower(), password_hash=password_hash)
    db.add(user)
    db.flush()
    return user
