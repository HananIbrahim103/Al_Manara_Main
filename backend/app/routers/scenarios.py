"""The five seeded scenarios, each started with one call.

Each call runs everything the system does on its own and stops where a named person must act.
It never answers a review and never decides: the response lists who must act next, with the
endpoint and an example body. Scenarios (a)-(c) pin Sahab Flash 2.0 so they behave the same
after scenario (e) registers a new version.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import audit_entry
from app.db import get_session
from app.models import Assessment, Concern, Deployment, Department, Review, UseCase, User, AIModel
from app.routers.evidence import register_version, resolve_version
from app.schemas import VersionIn
from app.security import get_current_user
from app.services import evaluation, governance, lifecycle, planning

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

SCENARIOS = {
    "a": dict(title="HR approves a document summariser as low risk on the fast track",
              department="HRL", use_case="HRL-SUMM", model="sahab-flash", version="2.0", run_as="daniel.okafor@hrl.gov.example"),
    "b": dict(title="Residency reuses the HR summariser for visa summaries: partial reuse, the tier rises, security and privacy "
                    "re-run, officer-verification condition",
              department="RID", use_case="RID-SUMM", model="sahab-flash", version="2.0", reuse="scenario_a",
              run_as="ahmed.alnuaimi@rid.gov.example"),
    "c": dict(title="Social reuses part of Traffic's Arabic assistant evaluation; accessibility and contestability run fresh",
              department="SCS", use_case="SCS-ASSIST", model="sahab-flash", version="2.0", run_as="reem.altunaiji@scs.gov.example"),
    "d": dict(title="An internal HR tool requested for a citizen-facing use: reuse is blocked, with the reason",
              department="SCS", use_case="SCS-POLICY-PUBLIC", model="sahab-flash", version="2.0", reuse="ASM-2026-0001",
              run_as="joseph.mathew@scs.gov.example"),
    "e": dict(title="A new model version alerts every department using it; a rise in Traffic objections triggers reassessment",
              department=None, model="sahab-flash", run_as="registry.admin@registry.gov.example"),
}

# Synthetic objections for scenario (e). Invented text; no real case.
OBJECTIONS = [
    ("appeal", "en", "The assistant told me my objection window had closed, but my fine was issued nine days ago."),
    ("appeal", "ar-gulf", "المساعد قال لي ما أقدر أعترض، والمخالفة عمرها أسبوع بس."),
    ("citizen_complaint", "en", "I was given a different fine amount from the one on the fines page."),
    ("appeal", "en", "My objection was not accepted because the assistant gave me the wrong upload link."),
    ("appeal", "ar-msa", "أعترض على المخالفة، وقد أبلغني المساعد بموعد نهائي غير صحيح."),
    ("citizen_complaint", "ar-gulf", "سألته عن المهلة وجاوبني جواب عام، ما عطاني تاريخ."),
    ("appeal", "en", "The assistant said speed-camera fines cannot be objected to. The website says they can."),
    ("citizen_complaint", "en", "Third time the assistant handed me to an officer after giving a wrong deadline."),
]

_DECISION_FOR = {"approve": "approved", "approve_with_conditions": "approved_with_conditions", "reject": "rejected"}


@router.get("")
async def list_scenarios(_: User = Depends(get_current_user)):
    return [{"key": key, "title": s["title"], "run_as": s["run_as"], "call": f"POST /scenarios/{key}/run"} for key, s in SCENARIOS.items()]


async def _people(session: AsyncSession) -> dict[int, User]:
    return {u.id: u for u in (await session.execute(select(User))).scalars()}


async def human_steps(session: AsyncSession, assessment: Assessment) -> list[dict]:
    """What named people must do next, in order, with an example request for each."""
    people = await _people(session)
    steps = []
    reviews = (await session.execute(select(Review).where(Review.assessment_id == assessment.id, Review.status == "pending")
                                     .order_by(Review.id))).scalars().all()
    for review in reviews:
        person = people[review.reviewer_id]
        steps.append({"who": person.full_name, "login_as": person.email, "role": review.reviewer_role,
                      "do": "Answer your review (all reviews were sent at the same time)",
                      "request": f"POST /reviews/{review.id}",
                      "example_body": {"status": "no_objection", "comment": "Checked the evidence in my area."}})
    concerns = (await session.execute(select(Concern).where(Concern.assessment_id == assessment.id, Concern.status == "open",
                                                            Concern.severity == "high").order_by(Concern.id))).scalars().all()
    _, approver = await governance.department_people(session, assessment.department_id)
    for concern in concerns:
        owner = people.get(concern.assigned_to_id) or approver
        steps.append({"who": owner.full_name, "login_as": owner.email, "do": f"Resolve high-severity concern: {concern.title}",
                      "request": f"POST /concerns/{concern.id}/resolve", "example_body": {"text": "What was changed or checked."},
                      "or": {"who": approver.full_name, "login_as": approver.email, "request": f"POST /concerns/{concern.id}/accept-risk",
                             "example_body": {"text": "Why this residual risk is acceptable."}}})
    if assessment.status in ("in_review", "awaiting_decision"):
        decision = _DECISION_FOR.get(assessment.recommendation or "", "approved_with_conditions")
        steps.append({"who": approver.full_name, "login_as": approver.email,
                      "do": "Decide (only the named approver can). The system's recommendation is advice, not a decision.",
                      "request": f"POST /assessments/{assessment.id}/decision",
                      "example_body": {"decision": decision, "reason": "Your reason, in your own words."}})
    return steps


async def _run_assessment(session: AsyncSession, key: str, user: User) -> dict:
    spec = SCENARIOS[key]
    use_case = (await session.execute(select(UseCase).where(UseCase.code == spec["use_case"]))).scalar_one()
    model, version = await resolve_version(session, spec["model"], spec["version"])
    source_id, source_note = None, "No source named: the registry searched every decided assessment of this model."
    if spec.get("reuse") == "scenario_a":
        summariser = (await session.execute(select(UseCase.id).where(UseCase.code == "HRL-SUMM"))).scalar_one()
        approved = (await session.execute(select(Assessment).where(
            Assessment.use_case_id == summariser, Assessment.model_version_id == version.id,
            Assessment.status.in_(("approved", "approved_with_conditions"))).order_by(Assessment.id.desc()))).scalars().first()
        if approved:
            source_id, source_note = approved.id, f"Reusing HR's approved summariser {approved.reference} (scenario a)."
        else:
            source_note = "Scenario (a) has not been approved yet, so the registry chose the best match itself. Run (a) to the decision first for the full story."
    elif spec.get("reuse"):
        source = (await session.execute(select(Assessment).where(Assessment.reference == spec["reuse"]))).scalar_one()
        source_id, source_note = source.id, f"Asked to reuse {source.reference}."

    assessment, _ = await planning.start_assessment(session, user, use_case, model, version, source_id)
    result = {"scenario": key, "title": spec["title"], "reuse": source_note, "assessment_id": assessment.id, "reference": assessment.reference}
    if assessment.status == "blocked":
        return {**result, "status": "blocked", "blocked_reason": assessment.summary.get("blocked_reason"),
                "next_step": assessment.summary.get("next_step"), "human_steps": []}

    await evaluation.claim(session, assessment.id, user)
    await evaluation.run_evaluation(assessment.id)
    await session.refresh(assessment)
    if assessment.status != "evaluated":
        return {**result, "status": assessment.status, "errors": assessment.summary.get("evaluation", {}).get("errors"), "human_steps": []}
    await governance.submit_for_review(session, assessment, user)
    await session.refresh(assessment)
    reuse = assessment.plan.get("counts", {})
    return {**result, "status": assessment.status, "risk_tier": assessment.risk_tier, "track": assessment.track,
            "recommendation": assessment.summary.get("recommendation"), "checks": assessment.summary.get("evaluation", {}).get("checks"),
            "reuse_counts": reuse, "suggested_conditions": assessment.summary.get("evaluation", {}).get("suggested_conditions"),
            "reviewers": assessment.summary.get("governance", {}).get("reviewers"),
            "human_steps": await human_steps(session, assessment),
            "see": [f"GET /assessments/{assessment.id}", f"GET /assessments/{assessment.id}/decision-record", f"GET /audit?assessment_id={assessment.id}"]}


async def _run_lifecycle(session: AsyncSession, user: User) -> dict:
    spec = SCENARIOS["e"]
    model = (await session.execute(select(AIModel).where(AIModel.slug == spec["model"]))).scalar_one()
    _, current = await resolve_version(session, model.slug, None)
    major, _, minor = current.version.partition(".")
    label = f"{major}.{int(minor or 0) + 1}"
    # Step 1: the provider ships a new version. Same endpoint a person would call; it fires the trigger.
    await register_version(model.slug, VersionIn(version=label, changelog="Provider release: new default model behind the same API (synthetic)."),
                           user, session)
    new_event = (await session.execute(select(lifecycle.MonitorEvent).where(lifecycle.MonitorEvent.trigger_type == "new_model_version")
                                       .order_by(lifecycle.MonitorEvent.id.desc()))).scalars().first()

    # Step 2: objections to Traffic's assistant rise. Synthetic citizen input, recorded as scripted.
    traffic = (await session.execute(select(Department).where(Department.code == "TRF"))).scalar_one()
    assistant = (await session.execute(select(UseCase).where(UseCase.code == "TRF-ASSIST"))).scalar_one()
    deployment = (await session.execute(select(Deployment).where(Deployment.department_id == traffic.id, Deployment.use_case_id == assistant.id,
                                                                 Deployment.status.in_(lifecycle.LIVE)).order_by(Deployment.id))).scalars().first()
    if deployment is None:
        raise HTTPException(409, "Traffic has no live deployment of its assistant. Reseed (python -m app.seed --reset) to run scenario (e) again.")
    spike = None
    for source, language, text in OBJECTIONS:
        _, fired = await lifecycle.add_feedback(session, deployment, source=source, language=language, text=text, user=None, scripted=True)
        spike = spike or fired
    session.add(audit_entry("scenario.run", user=user, details={"scenario": "e", "new_version": label, "objections_added": len(OBJECTIONS)}))
    await session.commit()

    departments = {d.id: d for d in (await session.execute(select(Department))).scalars()}
    alerts = (await session.execute(select(lifecycle.Alert).where(lifecycle.Alert.event_id >= new_event.id).order_by(lifecycle.Alert.id))).scalars().all()
    await session.refresh(deployment)
    people = await _people(session)
    officer = next(u for u in people.values() if u.email == "salma.alblooshi@trf.gov.example")
    return {
        "scenario": "e", "title": spec["title"],
        "new_version": f"{model.name} {label}",
        "alerts": [{"id": a.id, "department": departments[a.department_id].code, "deployment_id": a.deployment_id, "severity": a.severity,
                    "action_required": a.action_required, "title": a.title} for a in alerts],
        "departments_alerted_about_new_version": sorted({departments[a.department_id].code for a in alerts if a.event_id == new_event.id}),
        "traffic_deployment": {"id": deployment.id, "status": deployment.status, "reason": deployment.status_reason},
        "complaint_spike": spike,
        "human_steps": [
            {"who": officer.full_name, "login_as": officer.email, "do": "Start the reassessment Traffic was sent back for",
             "request": f"POST /deployments/{deployment.id}/reassess", "example_body": {}},
            {"who": "Each alerted department", "do": "Acknowledge the new-version alert", "request": "POST /alerts/{id}/acknowledge",
             "example_body": {"reason": "Seen. We stay pinned until the new version is assessed."}},
        ],
        "see": ["GET /alerts?status=open", f"GET /deployments/{deployment.id}", "GET /metrics"],
    }


@router.post("/{key}/run")
async def run(key: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Run one scenario up to the point where named people must act; the response says who and how."""
    key = key.lower()
    spec = SCENARIOS.get(key)
    if spec is None:
        raise HTTPException(404, f"Scenarios are {', '.join(SCENARIOS)}")
    if key == "e":
        if user.role != "admin":
            raise HTTPException(403, f"Scenario (e) is run by the registry administrator ({spec['run_as']}).")
        return await _run_lifecycle(session, user)
    department = await session.get(Department, user.department_id) if user.department_id else None
    if department is None or department.code != spec["department"]:
        raise HTTPException(403, f"Scenario ({key}) is run by someone from {spec['department']}, for example {spec['run_as']}: "
                                 "only the department that owns the use case can start its assessment.")
    return await _run_assessment(session, key, user)
