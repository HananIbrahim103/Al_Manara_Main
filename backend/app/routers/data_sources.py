"""Open data sources (Bayanat): register, link to a Use-Case Card, inspect, check for updates."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import DataSource, TestCase, UseCase, User
from app.security import get_current_user, require_admin
from app.services import datagen, opendata

router = APIRouter(tags=["open data"])


class DataSourceIn(BaseModel):
    dataset: str = Field(description="Bayanat dataset page URL, or its id (the part after ?id=)")
    key: str = Field(pattern=r"^[A-Za-z0-9-]{3,48}$", description="Short readable key, e.g. TRF-ACCIDENT-TYPE")


class LinkIn(BaseModel):
    data_source: str = Field(description="Data source key or id")


async def _summary(session: AsyncSession, ds: DataSource) -> dict:
    use_cases = await opendata.linked_use_cases(session, ds.id)
    cases = (await session.execute(select(func.count()).select_from(TestCase).where(
        TestCase.origin == datagen.ORIGIN, TestCase.meta["data_source_id"].as_integer() == ds.id,
        TestCase.meta["superseded"].as_boolean().is_not(True)))).scalar_one()
    return {"id": ds.id, "key": ds.key, "portal": ds.portal, "title": ds.title, "publisher": ds.publisher, "topics": ds.topics,
            "page_url": ds.page_url, "licence_url": ds.licence_url, "last_updated": ds.last_updated, "fetched_at": ds.fetched_at,
            "status": ds.status, "last_error": ds.last_error, "rows": ds.total_rows, "measure": ds.measure,
            "dimensions": ds.dimensions, "checksum": ds.checksum, "versions_seen": len(ds.history) + 1,
            "use_cases": [u.code for u in use_cases], "active_test_cases": cases}


@router.get("/data-sources")
async def list_sources(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Every published table in the registry, who relies on it, and how many test cases it currently gives."""
    rows = (await session.execute(select(DataSource).order_by(DataSource.id))).scalars().all()
    return [await _summary(session, ds) for ds in rows]


@router.get("/data-sources/{key}")
async def get_source(key: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """One table: metadata, the columns found, the first 20 rows, earlier versions, and its current test cases."""
    ds = await opendata.get_source(session, key)
    cases = (await session.execute(select(TestCase).where(TestCase.origin == datagen.ORIGIN,
                                                          TestCase.meta["data_source_id"].as_integer() == ds.id)
                                   .order_by(TestCase.id))).scalars().all()
    return {**await _summary(session, ds), "columns": ds.columns, "sample_rows": ds.rows[:20], "history": ds.history,
            "resource": {"name": ds.resource_name, "file_ref": ds.file_ref},
            "test_cases": [{"id": c.id, "check_key": c.check_key, "language": c.language, "kind": c.meta.get("kind"),
                            "computed_answer": c.meta.get("computed_answer"), "superseded": bool(c.meta.get("superseded")),
                            "prompt": c.prompt} for c in cases]}


@router.post("/data-sources", status_code=201)
async def register_source(body: DataSourceIn, user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    """Registry administrator adds a Bayanat dataset. It is fetched now; its first usable table is saved as a snapshot."""
    ds = await opendata.register(session, user, body.dataset, body.key)
    return await _summary(session, ds)


async def _use_case(session: AsyncSession, code: str) -> UseCase:
    use_case = (await session.execute(select(UseCase).where(UseCase.code == code.upper()))).scalar_one_or_none()
    if use_case is None:
        raise HTTPException(404, f"No use case with code {code}")
    return use_case


@router.get("/use-cases/{code}/data-sources")
async def use_case_sources(code: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    use_case = await _use_case(session, code)
    return [await _summary(session, ds) for ds in await opendata.sources_of(session, use_case.id)]


@router.post("/use-cases/{code}/data-sources", status_code=201)
async def link_source(code: str, body: LinkIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """The owning department says its service relies on this table. Test cases are written from it at once."""
    use_case = await _use_case(session, code)
    ds = await opendata.get_source(session, body.data_source)
    written = await opendata.link(session, user, use_case, ds)
    return {"use_case": use_case.code, "data_source": ds.key, "test_cases_written": written}


@router.delete("/use-cases/{code}/data-sources/{key}", status_code=204)
async def unlink_source(code: str, key: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    await opendata.unlink(session, user, await _use_case(session, code), await opendata.get_source(session, key))


@router.post("/data-sources/{key}/refresh")
async def refresh_source(key: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Check the portal for a new version of this table. A content change rewrites its test cases and sends every
    live deployment that relies on it back for reassessment (trigger `data_source_change`)."""
    if user.role not in ("admin", "reviewer"):
        raise HTTPException(403, "Reviewers and the registry administrator can check data sources.")
    return await opendata.refresh(session, await opendata.get_source(session, key), user)


@router.post("/data-sources/check-updates")
async def check_all(user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    """Check every registered table against the portal. Meant to run on a schedule."""
    rows = (await session.execute(select(DataSource).order_by(DataSource.id))).scalars().all()
    return [await opendata.refresh(session, ds, user) for ds in rows]
