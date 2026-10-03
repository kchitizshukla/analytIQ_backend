"""Shared API dependencies."""
from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.errors import api_error
from app.core.security import read_session_token
from app.models import Dataset, User
from app.repositories import dataset_repo, user_repo


def get_dataset_or_404(dataset_id: uuid.UUID, db: Session = Depends(get_db)) -> Dataset:
    ds = dataset_repo.get_dataset(db, dataset_id)
    if not ds:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Dataset not found")
    if not ds.storage_path:
        raise HTTPException(status.HTTP_409_CONFLICT, "Dataset has no stored file")
    return ds


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """Resolve the authenticated user from the signed session cookie.

    Raises 401 if there is no valid session.
    """
    token = request.cookies.get(settings.session_cookie_name)
    user_id = read_session_token(token)
    if not user_id:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED, "NOT_AUTHENTICATED", "Not authenticated."
        )
    user = user_repo.get_by_id(db, user_id)
    if not user:
        raise api_error(
            status.HTTP_401_UNAUTHORIZED, "NOT_AUTHENTICATED", "Not authenticated."
        )
    return user
