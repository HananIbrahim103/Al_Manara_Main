"""Start an assessment: tier, evidence summary, registry search, reuse decision and plan."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AgentRun, Assessment, ComplianceFinding, ComplianceRule, TestCase, TestRun, UseCase, User
from app.routers.evidence import resolve_version
from app.routers.registry import get_assessment
from app.schemas import AssessmentDetail, AssessmentStart
from app.security import get_current_user
from app.services import evaluation, planning

router = APIRouter(prefix="/assessments", tags=["assessments"])


async def _inputs(session: AsyncSession, body: AssessmentStart):
    use_case = (await session.execute(select(UseCase).where(UseCase.code == body.use_case_code.upper()))).scalar_one_or_none()
    if use_case is None:
        raise HTTPException(404, f"No use case with code {body.use_case_code}")
    model, version = await resolve_version(session, body.model_slug, body.version)
    return use_case, model, version


@router.post("/preview")
async def preview_assessment(body: AssessmentStart, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """What would happen, without saving anything: tier, evidence gaps, every reuse decision with reasons, and the plan."""
    use_case, model, version = await _inputs(session, body)
    result = await planning.compute(session, use_case, version, body.reuse_from_assessment_id)
    return {"use_case": use_case.code, "model": model.slug, "version": version.version,
            "would_be_blocked": result.requested_blocked, **planning.preview_payload(result)}


@router.post("", response_model=AssessmentDetail, status_code=201)
async def start_assessment(body: AssessmentStart, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Start an assessment for one of your department's use cases.

    Ends as `planned` (ready for evaluation, with reused evidence already attached) or `blocked`
    (you asked to reuse a specific approval and the context does not allow it).
    """
    use_case, model, version = await _inputs(session, body)
    assessment, _ = await planning.start_assessment(session, user, use_case, model, version, body.reuse_from_assessment_id)
    return await get_assessment(assessment.id, session)


@router.get("/{assessment_id}", response_model=AssessmentDetail)
async def read_assessment(assessment_id: int, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await get_assessment(assessment_id, session)


# ───────────── Phase 3: evaluation ─────────────

@router.post("/{assessment_id}/evaluate", status_code=202)
async def evaluate(assessment_id: int, wait: bool = False, user: User = Depends(get_current_user),
                   session: AsyncSession = Depends(get_session)):
    """Run the evaluation agents in parallel: Testing & Red-Team, Citizen Impact & Challenge, Compliance & Procurement.

    Returns at once; poll `GET /assessments/{id}` until `status` is `evaluated` (or `failed`).
    With `wait=true` the call returns only when the evaluation has finished.
    """
    assessment = await evaluation.claim(session, assessment_id, user)
    if wait:
        await evaluation.run_evaluation(assessment_id)
        await session.refresh(assessment)
    else:
        evaluation.start_in_background(assessment_id)
    return {"assessment_id": assessment_id, "reference": assessment.reference, "status": assessment.status,
            "evaluation": assessment.summary.get("evaluation") if wait else None}


async def _exists(session: AsyncSession, assessment_id: int) -> None:
    if await session.get(Assessment, assessment_id) is None:
        raise HTTPException(404, "No such assessment")


@router.get("/{assessment_id}/test-runs")
async def test_runs(assessment_id: int, check: str | None = None, failed_only: bool = False,
                    _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Every test case that was run: the prompt, the model's answer, the score and why."""
    await _exists(session, assessment_id)
    query = (select(TestRun, TestCase).join(TestCase, TestCase.id == TestRun.test_case_id)
             .where(TestRun.assessment_id == assessment_id).order_by(TestCase.check_key, TestRun.id))
    if check:
        query = query.where(TestCase.check_key == check)
    rows = (await session.execute(query)).all()
    return [{"id": run.id, "check_key": case.check_key, "language": case.language, "origin": case.origin, "test_case_id": case.id,
             "prompt": case.prompt, "expected": case.expected, "model_output": run.model_output, "score": run.score,
             "passed": run.passed, "notes": run.judge_notes, "latency_ms": run.latency_ms, "error": run.error}
            for run, case in rows if not failed_only or run.passed is not True]


@router.get("/{assessment_id}/compliance")
async def compliance_findings(assessment_id: int, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Every compliance and procurement rule that was evaluated, with its status and the evidence it relied on."""
    await _exists(session, assessment_id)
    rows = (await session.execute(
        select(ComplianceFinding, ComplianceRule).join(ComplianceRule, ComplianceRule.id == ComplianceFinding.rule_id)
        .where(ComplianceFinding.assessment_id == assessment_id).order_by(ComplianceRule.id))).all()
    return [{"rule": rule.code, "check_key": rule.check_key, "title": rule.title, "requirement": rule.requirement,
             "source_ref": rule.source_ref, "severity": rule.severity, "status": finding.status, "note": finding.note,
             "evidence_refs": finding.evidence_refs} for finding, rule in rows]


@router.get("/{assessment_id}/agent-runs")
async def agent_runs(assessment_id: int, agent: str | None = None, _: User = Depends(get_current_user),
                     session: AsyncSession = Depends(get_session)):
    """The audit trail of every agent step: input, output, model, tokens, cost, time, attempts and errors."""
    await _exists(session, assessment_id)
    query = select(AgentRun).where(AgentRun.assessment_id == assessment_id).order_by(AgentRun.id)
    if agent:
        query = query.where(AgentRun.agent == agent)
    return [{"id": r.id, "agent": r.agent, "step": r.step, "llm_model": r.llm_model, "status": r.status, "attempts": r.attempts,
             "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens, "cost_usd": r.cost_usd,
             "duration_ms": r.duration_ms, "error": r.error, "input": r.input, "output": r.output, "created_at": r.created_at}
            for r in (await session.execute(query)).scalars()]
