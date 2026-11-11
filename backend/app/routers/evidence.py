"""Agent 2, evidence half: register models and normalise provider evidence."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog
from app.audit import audit_entry
from app.db import get_session
from app.models import AIModel, ModelVersion, ProviderEvidence, User
from app.schemas import EvidenceCorrection, EvidenceOut, EvidenceSubmission, ModelIn, ModelOut, ModelVersionOut, VersionIn
from app.security import get_current_user
from app.services import evidence as evidence_service

router = APIRouter(prefix="/models", tags=["evidence"])

_NOTHING_YET = "Provider supplied nothing for this field. Unknown is treated as a risk."


def _require_evidence_role(user: User, what: str) -> None:
    """Provider evidence decides compliance results, so the person asking for an assessment cannot write it themselves."""
    if user.role not in ("admin", "reviewer"):
        raise HTTPException(403, f"Only a named reviewer or the registry administrator can {what}.")


def _blank_evidence(version_id: int) -> list[ProviderEvidence]:
    """A new version starts with every field missing: nothing is assumed from an earlier version."""
    return [ProviderEvidence(model_version_id=version_id, field=field, status="missing", value={}, source="", note=_NOTHING_YET)
            for field in catalog.EVIDENCE_FIELDS]


async def _model(session: AsyncSession, slug: str) -> AIModel:
    model = (await session.execute(select(AIModel).where(AIModel.slug == slug))).scalar_one_or_none()
    if model is None:
        raise HTTPException(404, f"No model with slug {slug}")
    return model


async def _version(session: AsyncSession, model: AIModel, version: str) -> ModelVersion:
    row = (await session.execute(
        select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.version == version))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"{model.name} has no version {version}")
    return row


async def resolve_version(session: AsyncSession, slug: str, version: str | None) -> tuple[AIModel, ModelVersion]:
    """The named version, or the current one."""
    model = await _model(session, slug)
    if version:
        return model, await _version(session, model, version)
    current = (await session.execute(
        select(ModelVersion).where(ModelVersion.model_id == model.id, ModelVersion.status == "current")
        .order_by(ModelVersion.id.desc()))).scalars().first()
    if current is None:
        raise HTTPException(409, f"{model.name} has no current version")
    return model, current


@router.post("", response_model=ModelOut, status_code=201)
async def register_model(body: ModelIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Put a model in: name, provider and the OpenRouter id used to test it. Evidence starts as all missing."""
    if (await session.execute(select(AIModel.id).where(AIModel.slug == body.slug))).scalar_one_or_none():
        raise HTTPException(409, f"A model with slug {body.slug} is already registered")
    model = AIModel(**body.model_dump(exclude={"version"}))
    session.add(model)
    await session.flush()
    version = ModelVersion(model_id=model.id, version=body.version, status="current", changelog="Initial registry entry.")
    session.add(version)
    await session.flush()
    session.add_all(_blank_evidence(version.id))
    session.add(audit_entry("model.registered", user=user, entity_type="model", entity_id=model.id,
                            details={"slug": model.slug, "version": body.version}))
    await session.commit()
    return model


@router.post("/{slug}/versions", response_model=ModelVersionOut, status_code=201)
async def register_version(slug: str, body: VersionIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Record a new provider version. Earlier versions become superseded; their evidence does not carry over.
    Every department using the model gets an alert (lifecycle trigger `new_model_version`)."""
    _require_evidence_role(user, "register a model version")
    model = await _model(session, slug)
    existing = (await session.execute(select(ModelVersion).where(ModelVersion.model_id == model.id))).scalars().all()
    if any(v.version == body.version for v in existing):
        raise HTTPException(409, f"{model.name} {body.version} is already registered")
    for old in existing:
        if old.status == "current":
            old.status = "superseded"
    version = ModelVersion(model_id=model.id, version=body.version, status="current", changelog=body.changelog)
    session.add(version)
    await session.flush()
    session.add_all(_blank_evidence(version.id))
    session.add(audit_entry("model.version_registered", user=user, entity_type="model_version", entity_id=version.id,
                            details={"slug": slug, "version": body.version}))
    # Agent 8: every department using this model is alerted in the same transaction.
    from app.services import lifecycle
    await lifecycle.on_new_version(session, model, version, user)
    await session.commit()
    return version


@router.post("/{slug}/versions/{version}/evidence")
async def submit_evidence(slug: str, version: str, body: EvidenceSubmission,
                          user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Submit provider documents. They are converted into the standard format; unsupported and missing claims are flagged."""
    _require_evidence_role(user, "submit provider evidence")
    model = await _model(session, slug)
    row = await _version(session, model, version)
    documents = [evidence_service.ProviderDocument(**d.model_dump()) for d in body.documents]
    result = await evidence_service.normalise_documents(session, row, f"{model.name} {version}", documents)
    session.add(audit_entry("evidence.submitted", user=user, entity_type="model_version", entity_id=row.id,
                            details={"documents": [{"title": d.title, "kind": d.kind} for d in documents],
                                     "changes": result["changes"], "discarded": len(result["discarded_extractions"]),
                                     "failed_documents": result["failed_documents"]}))
    await session.commit()
    return {"model": slug, "version": version, **result}


@router.get("/{slug}/versions/{version}/evidence/summary")
async def evidence_summary(slug: str, version: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Counts by status and every gap with its risk in plain words."""
    model = await _model(session, slug)
    row = await _version(session, model, version)
    rows = (await session.execute(select(ProviderEvidence).where(ProviderEvidence.model_version_id == row.id))).scalars().all()
    return {"model": slug, "version": version, **evidence_service.summarise(list(rows))}


@router.put("/{slug}/versions/{version}/evidence/{field}", response_model=EvidenceOut)
async def correct_evidence(slug: str, version: str, field: str, body: EvidenceCorrection,
                           user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """A named person sets one field after checking the source. The change and the reason go to the audit log."""
    _require_evidence_role(user, "set an evidence field")
    if field not in catalog.EVIDENCE_FIELDS:
        raise HTTPException(404, f"'{field}' is not an evidence field")
    model = await _model(session, slug)
    row = await _version(session, model, version)
    evidence = (await session.execute(select(ProviderEvidence).where(
        ProviderEvidence.model_version_id == row.id, ProviderEvidence.field == field))).scalar_one_or_none()
    if evidence is None:
        evidence = ProviderEvidence(model_version_id=row.id, field=field, status="missing", value={})
        session.add(evidence)
    before = evidence.status
    evidence.status, evidence.value, evidence.source = body.status, body.value, body.source
    evidence.note = f"{body.note} (set by {user.full_name}, {user.title})"
    session.add(audit_entry("evidence.corrected", user=user, entity_type="model_version", entity_id=row.id,
                            details={"field": field, "from": before, "to": body.status, "note": body.note}))
    await session.commit()
    return evidence
