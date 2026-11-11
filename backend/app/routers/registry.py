"""The shared registry: past assessments, deployments, incidents and lessons.

Every logged-in user from every department can read all of it. That is the point (R4):
what one department learned is visible to the others.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog
from app.db import get_session
from app.models import (
    AIModel, Approval, Assessment, AuditLog, CheckResult, Concern, DecisionRecord, Department,
    Deployment, Feedback, Incident, Lesson, ManualBaseline, ModelVersion, ReuseDecision, Review,
    StepTiming, TestCase, TestSet, UseCase,
)
from app.schemas import (
    AssessmentDetail, AssessmentOut, AuditOut, BaselineOut, DeploymentOut, FeedbackOut,
    IncidentOut, LessonOut, TestSetDetail, TestSetOut,
)
from app.security import get_current_user

router = APIRouter(tags=["registry"], dependencies=[Depends(get_current_user)])


async def _dept_id(session: AsyncSession, code: str) -> int:
    dept_id = (await session.execute(select(Department.id).where(Department.code == code.upper()))).scalar_one_or_none()
    if dept_id is None:
        raise HTTPException(404, f"No department with code {code}")
    return dept_id


async def _version_ids(session: AsyncSession, slug: str) -> list[int]:
    query = select(ModelVersion.id).join(AIModel, AIModel.id == ModelVersion.model_id).where(AIModel.slug == slug)
    return list((await session.execute(query)).scalars().all())


@router.get("/registry/assessments", response_model=list[AssessmentOut])
async def list_assessments(
    department: str | None = None,
    model: str | None = None,
    status: str | None = None,
    risk_tier: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Assessment).order_by(Assessment.started_at.desc())
    if department:
        query = query.where(Assessment.department_id == await _dept_id(session, department))
    if model:
        query = query.where(Assessment.model_version_id.in_(await _version_ids(session, model)))
    if status:
        query = query.where(Assessment.status == status)
    if risk_tier:
        query = query.where(Assessment.risk_tier == risk_tier)
    return (await session.execute(query)).scalars().all()


@router.get("/registry/assessments/{assessment_id}", response_model=AssessmentDetail)
async def get_assessment(assessment_id: int, session: AsyncSession = Depends(get_session)):
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "No such assessment")

    async def children(model, order_by=None):
        query = select(model).where(model.assessment_id == assessment.id).order_by(order_by if order_by is not None else model.id)
        return (await session.execute(query)).scalars().all()

    version = await session.get(ModelVersion, assessment.model_version_id)
    records = await children(DecisionRecord, DecisionRecord.version.desc())
    approvals = await children(Approval)
    return AssessmentDetail(
        **AssessmentOut.model_validate(assessment).model_dump(),
        use_case=await session.get(UseCase, assessment.use_case_id),
        model=await session.get(AIModel, version.model_id),
        model_version=version,
        department=await session.get(Department, assessment.department_id),
        reuse_decisions=await children(ReuseDecision),
        check_results=await children(CheckResult),
        reviews=await children(Review),
        concerns=await children(Concern),
        decision_record=records[0] if records else None,
        approval=approvals[0] if approvals else None,
        step_timings=await children(StepTiming),
    )


@router.get("/registry/deployments", response_model=list[DeploymentOut])
async def list_deployments(
    department: str | None = None, model: str | None = None, status: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    query = select(Deployment).order_by(Deployment.id)
    if department:
        query = query.where(Deployment.department_id == await _dept_id(session, department))
    if model:
        query = query.where(Deployment.model_version_id.in_(await _version_ids(session, model)))
    if status:
        query = query.where(Deployment.status == status)
    return (await session.execute(query)).scalars().all()


@router.get("/registry/incidents", response_model=list[IncidentOut])
async def list_incidents(department: str | None = None, model: str | None = None, session: AsyncSession = Depends(get_session)):
    query = select(Incident).order_by(Incident.occurred_at.desc())
    if department:
        query = query.where(Incident.department_id == await _dept_id(session, department))
    if model:
        query = query.where(Incident.model_version_id.in_(await _version_ids(session, model)))
    return (await session.execute(query)).scalars().all()


@router.get("/registry/lessons", response_model=list[LessonOut])
async def list_lessons(model: str | None = None, tag: str | None = None, session: AsyncSession = Depends(get_session)):
    query = select(Lesson).order_by(Lesson.created_at.desc())
    if model:
        model_id = (await session.execute(select(AIModel.id).where(AIModel.slug == model))).scalar_one_or_none()
        query = query.where(Lesson.model_id == model_id)
    if tag:
        query = query.where(Lesson.tags.contains([tag]))
    return (await session.execute(query)).scalars().all()


@router.get("/registry/feedback", response_model=list[FeedbackOut])
async def list_feedback(department: str | None = None, source: str | None = None, session: AsyncSession = Depends(get_session)):
    query = select(Feedback).order_by(Feedback.created_at.desc())
    if department:
        query = query.where(Feedback.department_id == await _dept_id(session, department))
    if source:
        query = query.where(Feedback.source == source)
    return (await session.execute(query)).scalars().all()


@router.get("/test-sets", response_model=list[TestSetOut])
async def list_test_sets(use_case: str | None = None, shared_only: bool = False, session: AsyncSession = Depends(get_session)):
    query = select(TestSet).order_by(TestSet.id)
    if use_case:
        use_case_id = (await session.execute(select(UseCase.id).where(UseCase.code == use_case.upper()))).scalar_one_or_none()
        query = query.where(TestSet.use_case_id == use_case_id)
    if shared_only:
        query = query.where(TestSet.use_case_id.is_(None))
    return (await session.execute(query)).scalars().all()


@router.get("/test-sets/{code}", response_model=TestSetDetail)
async def get_test_set(code: str, session: AsyncSession = Depends(get_session)):
    test_set = (await session.execute(select(TestSet).where(TestSet.code == code.upper()))).scalar_one_or_none()
    if test_set is None:
        raise HTTPException(404, f"No test set with code {code}")
    cases = (await session.execute(select(TestCase).where(TestCase.test_set_id == test_set.id).order_by(TestCase.id))).scalars().all()
    return TestSetDetail(**TestSetOut.model_validate(test_set).model_dump(), cases=cases)


@router.get("/compliance-rules")
async def list_compliance_rules(session: AsyncSession = Depends(get_session)):
    """The shared compliance and procurement checklist every department is assessed against."""
    from app.models import ComplianceRule
    rows = (await session.execute(select(ComplianceRule).order_by(ComplianceRule.id))).scalars().all()
    return [{"code": r.code, "check_key": r.check_key, "title": r.title, "requirement": r.requirement,
             "source_ref": r.source_ref, "severity": r.severity} for r in rows]


@router.get("/baselines", response_model=list[BaselineOut])
async def list_baselines(session: AsyncSession = Depends(get_session)):
    """Seeded manual timings per step and tier: the 'before' side of the time-saved metric."""
    return (await session.execute(select(ManualBaseline).order_by(ManualBaseline.id))).scalars().all()


@router.get("/catalog")
async def get_catalog():
    """The shared vocabulary every department uses: checks, tiers, evidence fields, triggers."""
    return {
        "risk_tiers": catalog.RISK_TIERS,
        "track_for_tier": catalog.TRACK_FOR_TIER,
        "checks": [{"key": key, "agent": agent, "title": title} for key, (agent, title) in catalog.CHECKS.items()],
        "track_checks": catalog.TRACK_CHECKS,
        "evidence_fields": catalog.EVIDENCE_FIELDS,
        "evidence_statuses": catalog.EVIDENCE_STATUSES,
        "reviewer_roles": catalog.REVIEWER_ROLES,
        "trigger_types": catalog.TRIGGER_TYPES,
        "steps": catalog.STEPS,
        "card_options": {
            "audience_type": catalog.AUDIENCE_TYPES,
            "data_sensitivity": catalog.DATA_SENSITIVITY,
            "consequence_of_error": catalog.CONSEQUENCE,
            "autonomy_level": catalog.AUTONOMY,
            "human_oversight": catalog.OVERSIGHT,
        },
    }


@router.get("/audit", response_model=list[AuditOut])
async def list_audit(
    action: str | None = None, assessment_id: int | None = None, limit: int = 100, offset: int = 0,
    session: AsyncSession = Depends(get_session),
):
    """Read-only. There is no endpoint that edits or deletes audit rows, and the database refuses both."""
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(min(limit, 500)).offset(offset)
    if action:
        query = query.where(AuditLog.action == action)
    if assessment_id is not None:
        query = query.where(AuditLog.assessment_id == assessment_id)
    return (await session.execute(query)).scalars().all()
