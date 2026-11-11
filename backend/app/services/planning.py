"""Start of the pipeline: tier the use case, summarise evidence, search the registry, build the plan.

`compute` works everything out without saving (used for previews).
`start_assessment` saves it, with timings, agent-run records and audit entries.
"""
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog, llm
from app.audit import audit_entry
from app.models import (
    AgentRun, AIModel, Approval, Assessment, CheckResult, Concern, Department, Deployment, Incident,
    Lesson, ModelVersion, ProviderEvidence, ReuseDecision, StepTiming, UseCase, User,
)
from app.services import evidence as evidence_service
from app.services import reuse as reuse_engine
from app.services.tiering import TierResult, assess_tier, required_checks

_DECIDED = ("approved", "approved_with_conditions", "rejected")


@dataclass
class Computed:
    tier: TierResult
    evidence: dict
    decisions: list[dict]
    selected: dict | None
    requested_blocked: bool
    plan: dict
    registry_knowledge: dict
    timings: dict


async def _source(session: AsyncSession, assessment: Assessment) -> reuse_engine.Source:
    use_case = await session.get(UseCase, assessment.use_case_id)
    version = await session.get(ModelVersion, assessment.model_version_id)
    department = await session.get(Department, assessment.department_id)
    checks = {
        row.check_key: reuse_engine.SourceCheck(
            status=row.status, score=row.score, note=row.details.get("note", ""),
            origin_assessment_id=row.reused_from_assessment_id or assessment.id)
        for row in (await session.execute(select(CheckResult).where(CheckResult.assessment_id == assessment.id))).scalars()
    }
    approval = (await session.execute(select(Approval).where(Approval.assessment_id == assessment.id))).scalar_one_or_none()
    deployment = (await session.execute(select(Deployment).where(Deployment.assessment_id == assessment.id))).scalars().first()
    return reuse_engine.Source(
        assessment_id=assessment.id, reference=assessment.reference, department=department.code,
        use_case_title=use_case.title, status=assessment.status, model_version_id=version.id, version=version.version,
        context=reuse_engine.Context(
            use_case_id=use_case.id, audience_type=use_case.audience_type, data_sensitivity=use_case.data_sensitivity,
            vulnerable_users=use_case.vulnerable_users, risk_tier=assessment.risk_tier, thresholds=use_case.thresholds),
        checks=checks, conditions=approval.conditions if approval else [],
        deployment_status=deployment.status if deployment else None, synthetic=bool(assessment.is_history), decided_at=assessment.completed_at,
    )


async def compute(session: AsyncSession, use_case: UseCase, version: ModelVersion,
                  requested_source_id: int | None = None, exclude_assessment_id: int | None = None) -> Computed:
    timings = {}

    # ---- Agent 1: risk tier ----
    clock = time.perf_counter()
    tier = assess_tier(use_case)
    required, dropped = required_checks(use_case, tier.track)
    timings["intake"] = time.perf_counter() - clock

    # ---- Agent 2: evidence summary ----
    clock = time.perf_counter()
    rows = (await session.execute(select(ProviderEvidence).where(ProviderEvidence.model_version_id == version.id))).scalars().all()
    evidence = evidence_service.summarise(list(rows), tier.risk_tier)
    timings["evidence"] = time.perf_counter() - clock

    # ---- Agent 2: registry search and reuse decision ----
    clock = time.perf_counter()
    target = reuse_engine.Context(
        use_case_id=use_case.id, audience_type=use_case.audience_type, data_sensitivity=use_case.data_sensitivity,
        vulnerable_users=use_case.vulnerable_users, risk_tier=tier.risk_tier, thresholds=use_case.thresholds)
    sibling_versions = select(ModelVersion.id).where(ModelVersion.model_id == version.model_id)
    query = select(Assessment).where(Assessment.model_version_id.in_(sibling_versions), Assessment.status.in_(_DECIDED))
    if exclude_assessment_id:
        query = query.where(Assessment.id != exclude_assessment_id)
    candidates = (await session.execute(query.order_by(Assessment.id))).scalars().all()

    if requested_source_id is not None and requested_source_id not in [c.id for c in candidates]:
        raise HTTPException(422, "The assessment you asked to reuse is not a decided assessment of this model.")

    # Seeded history carries invented scores: usable in mock mode (a demonstration), never with a real model.
    decisions = [reuse_engine.evaluate(target, version.id, version.version, required, await _source(session, c),
                                       allow_synthetic=llm.is_mock()) for c in candidates]
    for decision in decisions:
        decision["requested"] = decision["source_assessment_id"] == requested_source_id

    requested_blocked = False
    if requested_source_id is not None:
        requested = next(d for d in decisions if d["requested"])
        requested_blocked = requested["outcome"] == "blocked"
        selected = None if requested_blocked else requested
    else:
        selected = reuse_engine.choose(decisions)
    for decision in decisions:
        decision["selected"] = decision is selected
    timings["reuse_search"] = time.perf_counter() - clock

    # ---- the plan: what is reused, what runs fresh, and why ----
    reuse_map = selected["reuse_map"] if selected else {}
    rerun_reason = {}
    if selected:
        for reason in selected["reasons"]:
            if reason["effect"] == "rerun":
                rerun_reason.update({check: reason["reason"] for check in reason["checks"]})
    plan = {
        "required_checks": required,
        "dropped_checks": dropped,
        "reuse": [{"check": check, "agent": catalog.CHECKS[check][0], "from_reference": selected["source_reference"], **reuse_map[check]}
                  for check in required if check in reuse_map],
        "run": [{"check": check, "agent": catalog.CHECKS[check][0],
                 "reason": rerun_reason.get(check, "No reusable evidence in the registry for this context.")}
                for check in required if check not in reuse_map],
        "source": {"assessment_id": selected["source_assessment_id"], "reference": selected["source_reference"],
                   "outcome": selected["outcome"]} if selected else None,
        "inherited_conditions": selected["inherited_conditions"] if selected else [],
        "counts": {"required": len(required), "reused": len(reuse_map), "to_run": len(required) - len(reuse_map)},
    }

    # ---- what the registry already knows about this model ----
    version_ids = list((await session.execute(sibling_versions)).scalars())
    incidents = (await session.execute(select(Incident).where(Incident.model_version_id.in_(version_ids)).order_by(Incident.id))).scalars().all()
    lessons = (await session.execute(select(Lesson).where(Lesson.model_id == version.model_id).order_by(Lesson.id))).scalars().all()
    knowledge = {
        "incidents": [{"id": i.id, "title": i.title, "severity": i.severity, "status": i.status, "category": i.category} for i in incidents],
        "lessons": [{"id": lesson.id, "title": lesson.title, "detail": lesson.detail, "tags": lesson.tags} for lesson in lessons],
        "prior_rejections": [{"assessment_id": d["source_assessment_id"], "reference": d["source_reference"],
                              "department": d["source_department"], "use_case": d["source_use_case"]}
                             for d in decisions if d["reasons"][0]["rule"] == "R0"],
    }
    return Computed(tier=tier, evidence=evidence, decisions=decisions, selected=selected,
                    requested_blocked=requested_blocked, plan=plan, registry_knowledge=knowledge, timings=timings)


def preview_payload(result: Computed) -> dict:
    public = [{k: v for k, v in d.items() if k not in ("reuse_map", "same_audience")} for d in result.decisions]
    return {**result.tier.as_dict(), "evidence": result.evidence, "reuse_decisions": public,
            "plan": result.plan, "registry_knowledge": result.registry_knowledge}


async def start_assessment(session: AsyncSession, user: User, use_case: UseCase, model: AIModel, version: ModelVersion,
                           requested_source_id: int | None) -> tuple[Assessment, Computed]:
    if user.department_id != use_case.department_id:
        raise HTTPException(403, "Only the department that owns the use case can start its assessment; accountability stays with that department.")

    assessment = Assessment(
        reference=f"tmp-{uuid.uuid4().hex[:12]}", use_case_id=use_case.id, model_version_id=version.id,
        department_id=use_case.department_id, requested_by_id=user.id, status="draft")
    session.add(assessment)
    await session.flush()
    assessment.reference = f"ASM-{datetime.now(timezone.utc).year}-{assessment.id:04d}"

    result = await compute(session, use_case, version, requested_source_id, exclude_assessment_id=assessment.id)
    tier, plan = result.tier, result.plan

    assessment.risk_tier, assessment.track, assessment.tier_rationale = tier.risk_tier, tier.track, tier.rationale
    assessment.plan = plan
    assessment.summary = {"evidence": result.evidence, "registry_knowledge": result.registry_knowledge}
    if result.requested_blocked:
        blocked = next(d for d in result.decisions if d["requested"])
        assessment.status = "blocked"
        assessment.completed_at = datetime.now(timezone.utc)
        assessment.summary["blocked_reason"] = blocked["reasons"][0]["reason"]
        assessment.summary["next_step"] = "Start a new assessment without naming a source; the registry will offer any evidence that does match."
    else:
        assessment.status = "planned"

    for decision in result.decisions:
        session.add(ReuseDecision(
            assessment_id=assessment.id, source_assessment_id=decision["source_assessment_id"], outcome=decision["outcome"],
            reasons=decision["reasons"], reused_checks=decision["reused_checks"], rerun_checks=decision["rerun_checks"],
            requested=decision["requested"], selected=decision["selected"]))
        session.add(audit_entry("reuse.decided", agent="evidence_registry", entity_type="assessment", entity_id=assessment.id,
                                assessment_id=assessment.id,
                                details={"source": decision["source_reference"], "outcome": decision["outcome"],
                                         "selected": decision["selected"], "requested": decision["requested"],
                                         "reasons": [r["reason"] for r in decision["reasons"]]}))

    if assessment.status == "planned":
        # Reused evidence becomes check results now, re-read against this use case's own thresholds.
        for item in plan["reuse"]:
            session.add(CheckResult(
                assessment_id=assessment.id, agent=item["agent"], check_key=item["check"], score=item["score"],
                threshold=item["threshold"], status=item["status"], source="reused",
                reused_from_assessment_id=item["origin_assessment_id"],
                details={"note": item["note"], "reused_via": item["from_reference"]}))
        # Missing or unsupported provider evidence is an open concern until a reviewer closes it.
        for gap in result.evidence["gaps"]:
            if gap["severity"] == "low":
                continue
            session.add(Concern(
                assessment_id=assessment.id, raised_by_agent="evidence_registry", severity=gap["severity"],
                area=f"evidence:{gap['field']}",
                title=f"Provider evidence {gap['status']}: {gap['title']}", detail=gap["risk"]))

    runs = [
        ("intake_risk_tiering", "assign_tier", "intake",
         {"use_case": use_case.code}, tier.as_dict()),
        ("evidence_registry", "summarise_evidence", "evidence",
         {"model": model.slug, "version": version.version}, result.evidence),
        ("evidence_registry", "reuse_search", "reuse_search",
         {"model": model.slug, "version": version.version, "requested_source_id": requested_source_id},
         {"decisions": [{k: d[k] for k in ("source_reference", "outcome", "selected", "reused_checks", "rerun_checks")} for d in result.decisions],
          "plan_counts": plan["counts"]}),
    ]
    for agent, step, timing_key, run_input, run_output in runs:
        seconds = result.timings[timing_key]
        session.add(AgentRun(assessment_id=assessment.id, agent=agent, step=step, input=run_input, output=run_output,
                             llm_model=None, duration_ms=max(1, int(seconds * 1000))))
        session.add(StepTiming(assessment_id=assessment.id, step_key=timing_key, mode="automated", duration_seconds=round(seconds, 4)))

    session.add(audit_entry("assessment.started", user=user, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id,
                            details={"reference": assessment.reference, "use_case": use_case.code, "model": model.slug,
                                     "version": version.version, "requested_source_id": requested_source_id}))
    session.add(audit_entry("risk_tier.assigned", agent="intake_risk_tiering", entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id,
                            details={"risk_tier": tier.risk_tier, "track": tier.track,
                                     "rules": [r["rule"] for r in tier.rationale]}))
    session.add(audit_entry("plan.built", agent="evidence_registry", entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id, details={"status": assessment.status, **plan["counts"]}))
    await session.commit()
    return assessment, result
