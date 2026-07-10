import hmac
import os

from fastapi import Header, HTTPException


def require_admin_key(x_lei_admin_key: str | None = Header(default=None)) -> None:
    expected = os.getenv("LEI_ADMIN_API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="LEI_ADMIN_API_KEY is not configured")
    if not x_lei_admin_key or not hmac.compare_digest(x_lei_admin_key, expected):
        raise HTTPException(status_code=401, detail="Invalid admin API key")
