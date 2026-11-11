from collections.abc import AsyncIterator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings

_url = get_settings().sqlalchemy_url

# Async engine: used by the API and (later) the agent pipeline.
engine = create_async_engine(_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


def make_sync_session():
    """Sync session for the seed script and migrations (same driver, same URL)."""
    sync_engine = create_engine(_url, pool_pre_ping=True)
    return sessionmaker(sync_engine, expire_on_commit=False)()
