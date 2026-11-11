"""Login for seeded users.

All data is synthetic, so there are no passwords: you log in by choosing a seeded user and
get a signed token. What matters is enforced server-side from that token: who you are,
which department you belong to, and whether you are allowed to approve.
"""
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import User

_bearer = HTTPBearer(auto_error=False)
_ALGORITHM = "HS256"


def create_token(user: User) -> str:
    settings = get_settings()
    payload = {
        "sub": str(user.id),
        "exp": datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=_ALGORITHM)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_session),
) -> User:
    unauthorised = HTTPException(status.HTTP_401_UNAUTHORIZED, "Not logged in or token expired")
    if credentials is None:
        raise unauthorised
    try:
        payload = jwt.decode(credentials.credentials, get_settings().jwt_secret, algorithms=[_ALGORITHM])
        user = await session.get(User, int(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorised
    if user is None:
        raise unauthorised
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registry administrator only")
    return user
