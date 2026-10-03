"""Authentication routes — signup, login, logout, current user.

Credentials are validated against the database. The authentication decision is
made here on the backend (never in frontend JavaScript): login succeeds only
when the submitted password verifies against the stored bcrypt hash.

Sessions are carried in a signed, HTTP-only cookie so the token is never
exposed to JavaScript / localStorage.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.errors import api_error
from app.core.logging import get_logger
from app.core.security import create_session_token, hash_password, verify_password
from app.models import User
from app.repositories import user_repo
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    SignupRequest,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = get_logger("auth")


def _set_session_cookie(response: Response, user_id) -> None:
    token = create_session_token(user_id)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: SignupRequest, response: Response, db: Session = Depends(get_db)):
    if user_repo.get_by_email(db, payload.email):
        raise api_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_EXISTS",
            "An account with this email already exists.",
        )
    try:
        user = user_repo.create_user(
            db,
            name=payload.name,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        db.commit()
    except IntegrityError:
        # Unique constraint race — another request created the same email.
        db.rollback()
        raise api_error(
            status.HTTP_409_CONFLICT,
            "EMAIL_EXISTS",
            "An account with this email already exists.",
        )
    _set_session_cookie(response, user.id)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = user_repo.get_by_email(db, payload.email)
    # Verify regardless of whether the user exists (uniform error, no user
    # enumeration, and timing stays closer to constant).
    if not user or not verify_password(payload.password, user.password_hash):
        raise api_error(
            status.HTTP_401_UNAUTHORIZED,
            "INVALID_CREDENTIALS",
            "Invalid email or password.",
        )
    _set_session_cookie(response, user.id)
    return AuthResponse(user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(response: Response):
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_200_OK)
def change_password(
    payload: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change the authenticated user's password.

    The account is resolved from the session cookie (never from the frontend),
    the current password is verified against the stored bcrypt hash, and the new
    password is validated + re-hashed. Passwords are never logged or returned.
    """
    if not verify_password(payload.current_password, user.password_hash):
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "INVALID_CURRENT_PASSWORD",
            "Current password is incorrect.",
        )
    if verify_password(payload.new_password, user.password_hash):
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "SAME_PASSWORD",
            "New password must be different from your current password.",
        )
    user.password_hash = hash_password(payload.new_password)
    db.commit()
    logger.info("Password changed for user %s", user.id)  # id only — never the password
    return {"ok": True}
