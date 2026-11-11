"""Phase 4: reviews, concerns, decision record and the human decision."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Assessment, Concern, DecisionRecord, Review, UseCase, User
from app.routers.registry import get_assessment
from app.schemas import (
    AssessmentDetail, ConcernClose, ConcernIn, ConcernOut, DecisionIn, DecisionRecordOut, ReviewOut, ReviewResponse, SendBackIn,
)
from app.security import get_current_user
from app.services import governance

router = APIRouter(tags=["governance"])


@router.post("/assessments/{assessment_id}/submit-for-review", response_model=AssessmentDetail)
async def submit_for_review(assessment_id: int, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Agent 6. From `evaluated`: system recommendation by rule, reviewers chosen by role and risk tier
    (fast 2, standard 3, full all), every review sent at the same time, concerns routed to their owners,
    decision record built. Ends `in_review`."""
    assessment = await governance.load(session, assessment_id)
    await governance.submit_for_review(session, assessment, user)
    return await get_assessment(assessment_id, session)


@router.get("/reviews/inbox", response_model=list[dict])
async def review_inbox(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Reviews waiting for you, with what you are responsible for and the concerns assigned to you."""
    rows = (await session.execute(
        select(Review, Assessment, UseCase).join(Assessment, Assessment.id == Review.assessment_id)
        .join(UseCase, UseCase.id == Assessment.use_case_id)
        .where(Review.reviewer_id == user.id, Review.status == "pending", Assessment.status == "in_review").order_by(Review.id))).all()
    out = []
    for review, assessment, use_case in rows:
        mine = (await session.execute(select(Concern).where(Concern.assessment_id == assessment.id, Concern.assigned_to_id == user.id,
                                                            Concern.status == "open"))).scalars().all()
        out.append({"review_id": review.id, "assessment_id": assessment.id, "reference": assessment.reference,
                    "use_case": use_case.title, "risk_tier": assessment.risk_tier, "recommendation": assessment.recommendation,
                    "responsibilities": review.responsibilities, "why_you": review.selection_reason, "assigned_at": review.assigned_at,
                    "concerns_assigned_to_you": [{"id": c.id, "title": c.title, "severity": c.severity} for c in mine]})
    return out


@router.post("/reviews/{review_id}", response_model=ReviewOut)
async def answer_review(review_id: int, body: ReviewResponse, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    """Answer your review: no objection, concerns, or objection. Concerns and objections are always tracked as concerns;
    an objection is high severity and blocks approval until resolved or accepted as residual risk."""
    review = await session.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "No such review")
    await governance.respond(session, review, user, body.status, body.comment, [c.model_dump() for c in body.concerns])
    await session.refresh(review)
    return review


@router.post("/assessments/{assessment_id}/concerns", response_model=ConcernOut, status_code=201)
async def raise_concern(assessment_id: int, body: ConcernIn, user: User = Depends(get_current_user),
                        session: AsyncSession = Depends(get_session)):
    assessment = await governance.load(session, assessment_id)
    return await governance.raise_concern(session, assessment, user, body.model_dump())


async def _concern(session: AsyncSession, concern_id: int) -> Concern:
    concern = await session.get(Concern, concern_id)
    if concern is None:
        raise HTTPException(404, "No such concern")
    return concern


@router.post("/concerns/{concern_id}/resolve", response_model=ConcernOut)
async def resolve_concern(concern_id: int, body: ConcernClose, user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    """Close a concern with how it was resolved. The person it is assigned to, the person who raised it, or the approver."""
    return await governance.close_concern(session, await _concern(session, concern_id), user, body.text, accept_risk=False)


@router.post("/concerns/{concern_id}/accept-risk", response_model=ConcernOut)
async def accept_concern_as_residual_risk(concern_id: int, body: ConcernClose, user: User = Depends(get_current_user),
                                          session: AsyncSession = Depends(get_session)):
    """The department's named approver accepts a concern as residual risk, with the reason. Recorded by name."""
    return await governance.close_concern(session, await _concern(session, concern_id), user, body.text, accept_risk=True)


@router.get("/assessments/{assessment_id}/decision-record", response_model=DecisionRecordOut)
async def decision_record(assessment_id: int, version: int | None = None, _: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    """The Assurance Package: assumptions, limitations, evidence used, conditions, residual risk, accountable owner.
    Latest version by default; every earlier version is kept."""
    query = select(DecisionRecord).where(DecisionRecord.assessment_id == assessment_id)
    query = query.where(DecisionRecord.version == version) if version else query.order_by(DecisionRecord.version.desc())
    record = (await session.execute(query)).scalars().first()
    if record is None:
        raise HTTPException(404, "No decision record yet. It is built when the assessment is sent for review.")
    return record


@router.get("/assessments/{assessment_id}/decision-record/versions", response_model=list[DecisionRecordOut])
async def decision_record_versions(assessment_id: int, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return (await session.execute(select(DecisionRecord).where(DecisionRecord.assessment_id == assessment_id)
                                  .order_by(DecisionRecord.version))).scalars().all()


@router.get("/approvals/inbox", response_model=list[dict])
async def approval_inbox(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """For a department's named approver: assessments in review or waiting for your decision, and what still blocks them."""
    if not user.can_approve:
        return []
    rows = (await session.execute(select(Assessment, UseCase).join(UseCase, UseCase.id == Assessment.use_case_id)
                                  .where(Assessment.department_id == user.department_id,
                                         Assessment.status.in_(("in_review", "awaiting_decision"))).order_by(Assessment.id))).all()
    out = []
    for assessment, use_case in rows:
        blocking = (await session.execute(select(Concern).where(Concern.assessment_id == assessment.id, Concern.status == "open",
                                                                Concern.severity == "high"))).scalars().all()
        pending = (await session.execute(select(Review).where(Review.assessment_id == assessment.id, Review.status == "pending"))).scalars().all()
        out.append({"assessment_id": assessment.id, "reference": assessment.reference, "use_case": use_case.title,
                    "status": assessment.status, "risk_tier": assessment.risk_tier, "recommendation": assessment.recommendation,
                    "pending_reviews": len(pending), "open_high_concerns": [{"id": c.id, "title": c.title} for c in blocking],
                    "ready_to_decide": assessment.status == "awaiting_decision" and not blocking})
    return out


@router.post("/assessments/{assessment_id}/send-back", response_model=AssessmentDetail)
async def send_back(assessment_id: int, body: SendBackIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """The approver returns the assessment. It can then be evaluated again (`POST /assessments/{id}/evaluate`) and re-submitted."""
    assessment = await governance.load(session, assessment_id)
    await governance.send_back(session, assessment, user, body.reason)
    return await get_assessment(assessment_id, session)


@router.post("/assessments/{assessment_id}/decision", response_model=AssessmentDetail)
async def decide(assessment_id: int, body: DecisionIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Agent 7, the human decision. Only the owning department's named approver; a reason is required.
    Approval creates a deployment carrying its conditions."""
    assessment = await governance.load(session, assessment_id)
    await governance.decide(session, assessment, user, decision=body.decision, reason=body.reason, conditions=body.conditions,
                            risk_accepted_by_email=body.risk_accepted_by_email, override_recommendation=body.override_recommendation)
    return await get_assessment(assessment_id, session)
