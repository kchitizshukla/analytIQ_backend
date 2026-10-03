"""Consistent structured API errors.

Every error raised through :func:`api_error` serialises as::

    {"detail": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}}

The ``message`` is always safe to show to end users — it never leaks stack
traces, SQL, connection strings, secrets, or internal paths.
"""
from __future__ import annotations

from fastapi import HTTPException


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})
