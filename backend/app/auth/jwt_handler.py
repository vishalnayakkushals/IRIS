from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

ALGORITHM = "HS256"


def create_token(email: str, secret: str, expire_days: int = 14) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(days=expire_days)
    payload = {"sub": email, "exp": expire}
    return jwt.encode(payload, secret, algorithm=ALGORITHM)


def verify_token(token: str, secret: str) -> str:
    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
        email: str | None = payload.get("sub")
        if not email:
            raise ValueError("Token missing subject")
        return email
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc
