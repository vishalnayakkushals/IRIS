from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from backend.app.auth.dependencies import get_current_user
from backend.app.auth.jwt_handler import create_token
from backend.app.config import Settings, get_settings
from backend.app.db.platform_data import authenticate_platform_user, get_platform_user_profile
from backend.app.limiter import limiter
from backend.app.models.auth import LoginRequest, TokenResponse, UserMe

router = APIRouter()


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, settings: Settings = Depends(get_settings)) -> TokenResponse:
    user = await authenticate_platform_user(body.email, body.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_token(str(user.get("email", body.email)).strip(), settings.jwt_secret, settings.jwt_expire_days)
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserMe)
async def me(
    email: str = Depends(get_current_user),
) -> UserMe:
    profile = await get_platform_user_profile(email)
    full_name = str(profile.get("full_name", email)) if profile else email
    store_id = str(profile.get("store_id", "")) if profile else ""
    return UserMe(email=email, full_name=full_name, store_id=store_id)
