from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status

# Allow importing from src/iris/
_SRC = Path(__file__).resolve().parents[3] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from iris.store_registry import authenticate_user  # noqa: E402

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt_handler import create_token
from backend.app.config import Settings, get_settings
from backend.app.models.auth import LoginRequest, TokenResponse, UserMe

router = APIRouter()


def _lookup_user_profile(db_path: Path, email: str) -> tuple[str, str] | None:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT full_name, store_id FROM users WHERE lower(email)=lower(?)",
            (email.strip(),),
        ).fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return str(row[0] or email), str(row[1] or "")


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, settings: Settings = Depends(get_settings)) -> TokenResponse:
    user = authenticate_user(settings.db_path_obj, body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token(user.email, settings.jwt_secret, settings.jwt_expire_days)
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserMe)
def me(
    email: str = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> UserMe:
    profile = _lookup_user_profile(settings.db_path_obj, email)
    full_name = profile[0] if profile else email
    store_id = profile[1] if profile else ""
    return UserMe(email=email, full_name=full_name, store_id=store_id)
