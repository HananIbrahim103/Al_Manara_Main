"""Open data in the registry: snapshots of Bayanat tables, links to Use-Case Cards, test cases, update checks.

A Use-Case Card names the published tables its service relies on. Each linked table gives that use case
test cases with answers computed from the table (see datagen). When the portal publishes a new version of
a table, the old cases are marked superseded, new ones are written, and every live deployment of a linked
use case goes back for reassessment (lifecycle trigger `data_source_change`).
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit_entry
from app.models import DataSource, TestCase, TestSet, UseCase, UseCaseDataSource, User
from app.services import bayanat, datagen

SET_PREFIX = "DATA-"


def source_dict(ds: DataSource) -> dict:
    return {"title": ds.title, "publisher": ds.publisher, "rows": ds.rows, "measure": ds.measure,
            "dimensions": ds.dimensions, "checksum": ds.checksum}


def apply_snapshot(ds: DataSource, snap: bayanat.Snapshot) -> None:
    ds.portal, ds.portal_token = bayanat.PORTAL, snap.page.token
    ds.title, ds.publisher, ds.topics, ds.page_url = snap.page.title, snap.page.publisher, snap.page.topics, snap.page.page_url
    ds.licence_url, ds.last_updated = bayanat.TERMS_URL, snap.page.last_updated
    ds.resource_name, ds.file_ref = snap.resource.name, snap.resource.file_ref
    ds.columns, ds.measure, ds.dimensions = snap.table.columns, snap.table.measure, snap.table.dimensions
    ds.rows, ds.total_rows, ds.checksum = snap.table.rows, snap.table.total_rows, snap.checksum
    ds.fetched_at, ds.status, ds.last_error = datetime.now(timezone.utc), "ok", None


def case_rows(test_set_id: int, ds: DataSource, languages: list[str]) -> list[TestCase]:
    """Test cases for one use case from one table. Works for both the sync seed and the async API."""
    return [TestCase(test_set_id=test_set_id, check_key=d.check_key, language=d.language, prompt=d.prompt, expected=d.expected,
                     origin=datagen.ORIGIN, tags=[datagen.ORIGIN, ds.key, d.kind],
                     meta={"data_source_id": ds.id, "data_source_key": ds.key, "checksum": ds.checksum, "kind": d.kind,
                           "computed_answer": d.answer, "source_url": ds.page_url})
            for d in datagen.generate(source_dict(ds), languages)]


def data_set_for(use_case: UseCase, own_prompt: str) -> TestSet:
    return TestSet(code=f"{SET_PREFIX}{use_case.code}", title=f"Open-data cases for {use_case.title}", use_case_id=use_case.id,
                   system_prompt=(own_prompt or "You assist a UAE government department.") + datagen.DATA_INSTRUCTION,
                   description="Questions about published Bayanat tables. Answers are computed from the table by code, so these cases can fail a check.")


# ───────────── async helpers (API) ─────────────

async def get_source(session: AsyncSession, key_or_id: str) -> DataSource:
    by_id = key_or_id.isascii() and key_or_id.isdigit() and len(key_or_id) <= 9  # longer than any id: treat as a key, so 404
    query = select(DataSource).where(DataSource.id == int(key_or_id)) if by_id else \
        select(DataSource).where(DataSource.key == key_or_id.upper())
    ds = (await session.execute(query)).scalar_one_or_none()
    if ds is None:
        raise HTTPException(404, f"No data source {key_or_id}")
    return ds


async def _data_set(session: AsyncSession, use_case: UseCase) -> TestSet:
    code = f"{SET_PREFIX}{use_case.code}"
    existing = (await session.execute(select(TestSet).where(TestSet.code == code))).scalar_one_or_none()
    if existing:
        return existing
    own = (await session.execute(select(TestSet).where(TestSet.code == use_case.code))).scalar_one_or_none()
    test_set = data_set_for(use_case, own.system_prompt if own else "")
    session.add(test_set)
    await session.flush()
    return test_set


async def _supersede(session: AsyncSession, test_set_id: int, ds_id: int) -> int:
    cases = (await session.execute(select(TestCase).where(TestCase.test_set_id == test_set_id,
                                                          TestCase.origin == datagen.ORIGIN))).scalars().all()
    count = 0
    for case in cases:
        if case.meta.get("data_source_id") == ds_id and not case.meta.get("superseded"):
            case.meta = {**case.meta, "superseded": True}
            count += 1
    return count


async def build_cases(session: AsyncSession, use_case: UseCase, ds: DataSource) -> int:
    test_set = await _data_set(session, use_case)
    await _supersede(session, test_set.id, ds.id)
    rows = case_rows(test_set.id, ds, use_case.languages)
    session.add_all(rows)
    await session.flush()
    return len(rows)


async def linked_use_cases(session: AsyncSession, ds_id: int) -> list[UseCase]:
    return list((await session.execute(select(UseCase).join(UseCaseDataSource, UseCaseDataSource.use_case_id == UseCase.id)
                                       .where(UseCaseDataSource.data_source_id == ds_id).order_by(UseCase.id))).scalars())


async def sources_of(session: AsyncSession, use_case_id: int) -> list[DataSource]:
    return list((await session.execute(select(DataSource).join(UseCaseDataSource, UseCaseDataSource.data_source_id == DataSource.id)
                                       .where(UseCaseDataSource.use_case_id == use_case_id).order_by(DataSource.id))).scalars())


async def register(session: AsyncSession, user: User, dataset: str, key: str) -> DataSource:
    """Registry administrator adds a Bayanat dataset: fetched live, its table found and saved."""
    if (await session.execute(select(DataSource.id).where(DataSource.key == key.upper()))).scalar_one_or_none():
        raise HTTPException(409, f"A data source with key {key.upper()} already exists")
    try:
        snap = await bayanat.snapshot(dataset)
    except bayanat.BayanatError as exc:
        raise HTTPException(502, str(exc))
    if (await session.execute(select(DataSource.id).where(DataSource.file_ref == snap.resource.file_ref))).scalar_one_or_none():
        raise HTTPException(409, "This file is already registered.")
    ds = DataSource(key=key.upper(), measure="", file_ref="", page_url="", title="", portal_token="", checksum="")
    apply_snapshot(ds, snap)
    session.add(ds)
    await session.flush()
    session.add(audit_entry("data_source.registered", user=user, entity_type="data_source", entity_id=ds.id,
                            details={"key": ds.key, "title": ds.title, "publisher": ds.publisher, "rows": ds.total_rows,
                                     "checksum": ds.checksum, "page_url": ds.page_url}))
    await session.commit()
    return ds


async def link(session: AsyncSession, user: User, use_case: UseCase, ds: DataSource) -> int:
    if user.department_id != use_case.department_id:
        raise HTTPException(403, "Only the department that owns the use case can change its data sources.")
    if (await session.execute(select(UseCaseDataSource.id).where(UseCaseDataSource.use_case_id == use_case.id,
                                                                 UseCaseDataSource.data_source_id == ds.id))).scalar_one_or_none():
        raise HTTPException(409, "Already linked.")
    session.add(UseCaseDataSource(use_case_id=use_case.id, data_source_id=ds.id, linked_by_id=user.id))
    count = await build_cases(session, use_case, ds)
    session.add(audit_entry("data_source.linked", user=user, entity_type="use_case", entity_id=use_case.id,
                            details={"use_case": use_case.code, "data_source": ds.key, "cases_written": count}))
    await session.commit()
    return count


async def unlink(session: AsyncSession, user: User, use_case: UseCase, ds: DataSource) -> None:
    if user.department_id != use_case.department_id:
        raise HTTPException(403, "Only the department that owns the use case can change its data sources.")
    row = (await session.execute(select(UseCaseDataSource).where(UseCaseDataSource.use_case_id == use_case.id,
                                                                 UseCaseDataSource.data_source_id == ds.id))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Not linked.")
    await session.delete(row)
    test_set = (await session.execute(select(TestSet).where(TestSet.code == f"{SET_PREFIX}{use_case.code}"))).scalar_one_or_none()
    retired = await _supersede(session, test_set.id, ds.id) if test_set else 0
    session.add(audit_entry("data_source.unlinked", user=user, entity_type="use_case", entity_id=use_case.id,
                            details={"use_case": use_case.code, "data_source": ds.key, "cases_retired": retired}))
    await session.commit()


async def refresh(session: AsyncSession, ds: DataSource, user: User | None) -> dict:
    """Check the portal for a new version. Content change: new cases, and linked deployments go back for reassessment."""
    from app.services import lifecycle

    try:
        snap = await bayanat.snapshot(ds.portal_token)
    except bayanat.BayanatError as exc:
        ds.status, ds.last_error = "unreachable", str(exc)[:1000]
        session.add(audit_entry("data_source.check_failed", user=user, agent=None if user else lifecycle.MONITOR,
                                entity_type="data_source", entity_id=ds.id, details={"key": ds.key, "error": ds.last_error}))
        await session.commit()
        return {"key": ds.key, "changed": False, "error": ds.last_error}

    before = {"last_updated": ds.last_updated.isoformat() if ds.last_updated else None, "checksum": ds.checksum,
              "rows": ds.total_rows, "fetched_at": ds.fetched_at.isoformat() if ds.fetched_at else None}
    content_changed = snap.checksum != ds.checksum
    date_changed = snap.page.last_updated != ds.last_updated
    if not content_changed and not date_changed:
        ds.fetched_at, ds.status, ds.last_error = datetime.now(timezone.utc), "ok", None
        await session.commit()
        return {"key": ds.key, "changed": False, "last_updated": before["last_updated"]}

    ds.history = ds.history + [before]
    apply_snapshot(ds, snap)
    result = {"key": ds.key, "changed": True, "content_changed": content_changed, "before": before,
              "after": {"last_updated": ds.last_updated.isoformat() if ds.last_updated else None, "checksum": ds.checksum,
                        "rows": ds.total_rows}, "cases_rewritten": 0}
    if content_changed:
        for use_case in await linked_use_cases(session, ds.id):
            result["cases_rewritten"] += await build_cases(session, use_case, ds)
    result.update(await lifecycle.on_data_source_updated(session, ds, result))
    session.add(audit_entry("data_source.updated", user=user, agent=None if user else lifecycle.MONITOR, entity_type="data_source",
                            entity_id=ds.id, details={k: v for k, v in result.items() if k != "alerts"}))
    await session.commit()
    return result
