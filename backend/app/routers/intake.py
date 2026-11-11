"""Agent 1: Use-Case Intake & Risk Tiering."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog
from app.audit import audit_entry
from app.db import get_session
from app.models import Department, UseCase, User
from app.schemas import UseCaseIn, UseCaseOut
from app.security import get_current_user
from app.services.tiering import assess_tier, required_checks

router = APIRouter(tags=["intake and risk tier"])


def _tier_payload(card) -> dict:
    tier = assess_tier(card)
    required, dropped = required_checks(card, tier.track)
    return {**tier.as_dict(), "required_checks": required, "dropped_checks": dropped}


@router.post("/tier/preview")
async def preview_tier(card: UseCaseIn, _: User = Depends(get_current_user)):
    """Risk tier for a card that has not been saved yet, with every rule that fired."""
    return _tier_payload(card)


@router.post("/use-cases", response_model=UseCaseOut, status_code=201)
async def create_use_case(card: UseCaseIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Save a Use-Case Card for your own department. Thresholds you leave out take the shared defaults."""
    if user.department_id is None:
        raise HTTPException(403, "Use cases belong to a department; the registry administrator cannot create one.")
    department = await session.get(Department, user.department_id)
    data = card.model_dump()
    data["thresholds"] = {**catalog.DEFAULT_THRESHOLDS, **data["thresholds"]}
    use_case = UseCase(code=f"tmp-{user.id}", department_id=department.id, created_by_id=user.id, **data)
    session.add(use_case)
    await session.flush()
    use_case.code = f"{department.code}-UC-{use_case.id:03d}"
    tier = assess_tier(use_case)
    session.add(audit_entry("use_case.created", user=user, entity_type="use_case", entity_id=use_case.id,
                            details={"code": use_case.code, "title": use_case.title, "indicative_tier": tier.risk_tier}))
    await session.commit()
    return use_case


@router.get("/use-cases/{code}/tier")
async def use_case_tier(code: str, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Risk tier of a saved card, the rules behind it, and the checks that tier requires."""
    use_case = (await session.execute(select(UseCase).where(UseCase.code == code.upper()))).scalar_one_or_none()
    if use_case is None:
        raise HTTPException(404, f"No use case with code {code}")
    return {"use_case": use_case.code, **_tier_payload(use_case)}
