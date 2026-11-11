from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit_entry
from app.db import get_session
from app.models import User
from app.schemas import LoginIn, LoginOut, UserOut
from app.security import create_token, get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/users", response_model=list[UserOut])
async def login_choices(session: AsyncSession = Depends(get_session)):
    """Seeded users to choose from on the login screen (synthetic data, no passwords)."""
    return (await session.execute(select(User).order_by(User.department_id, User.id))).scalars().all()


@router.post("/login", response_model=LoginOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)):
    user = (await session.execute(select(User).where(User.email == body.email.strip().lower()))).scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "No seeded user with that email")
    session.add(audit_entry("auth.login", user=user, entity_type="user", entity_id=user.id))
    await session.commit()
    return LoginOut(access_token=create_token(user), user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return user
