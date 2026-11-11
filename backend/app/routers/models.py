from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIModel, ModelVersion, ProviderEvidence
from app.schemas import ModelDetail, ModelOut, ModelVersionOut, VersionDetail
from app.security import get_current_user

router = APIRouter(prefix="/models", tags=["models"], dependencies=[Depends(get_current_user)])

GAP_STATUSES = ("missing", "unsupported")


@router.get("", response_model=list[ModelOut])
async def list_models(session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(AIModel).order_by(AIModel.id))).scalars().all()


@router.get("/{slug}", response_model=ModelDetail)
async def get_model(slug: str, session: AsyncSession = Depends(get_session)):
    """A model with every version and its normalised provider evidence, gaps listed."""
    model = (await session.execute(select(AIModel).where(AIModel.slug == slug))).scalar_one_or_none()
    if model is None:
        raise HTTPException(404, f"No model with slug {slug}")
    versions = (
        await session.execute(select(ModelVersion).where(ModelVersion.model_id == model.id).order_by(ModelVersion.id))
    ).scalars().all()
    details = []
    for version in versions:
        evidence = (
            await session.execute(
                select(ProviderEvidence).where(ProviderEvidence.model_version_id == version.id).order_by(ProviderEvidence.id)
            )
        ).scalars().all()
        details.append(
            VersionDetail(
                **ModelVersionOut.model_validate(version).model_dump(),
                evidence=evidence,
                evidence_gaps=[e.field for e in evidence if e.status in GAP_STATUSES],
            )
        )
    return ModelDetail(**ModelOut.model_validate(model).model_dump(), versions=details)
