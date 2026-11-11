"""Agents 6 and 7: Governance Orchestrator and Human Approval.

Agent 6 (orchestrator) works out the system recommendation by rule, chooses reviewers by role and
risk tier from the owning department, sends every review at the same time, routes each concern to
the person responsible for it, and builds the decision record (the Assurance Package).

Agent 7 (approval) is a gate, not a decider: only the owning department's named approver can
approve, approve with conditions or reject, with a reason. Open high-severity concerns must first be
resolved or explicitly accepted as residual risk. There is no code path in which the system decides.
"""
import time
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog, llm
from app.audit import audit_entry
from app.models import (
    AIModel, Approval, Assessment, CheckResult, ComplianceFinding, ComplianceRule, Concern, DecisionRecord,
    Department, Deployment, ModelVersion, Review, StepTiming, TestCase, TestRun, UseCase, User,
)

ORCHESTRATOR, APPROVAL_GATE = "governance_orchestrator", "human_approval"

# Which checks each reviewer role is responsible for. Concerns in those areas are routed to them.
ROLE_AREAS = {
    "business_owner": ["task_accuracy", "human_oversight", "cost", "critic_review"],
    "security": ["prompt_injection", "pii_leakage", "data_residency", "vendor_lock_in"],
    "data_protection": ["pii_leakage", "sensitive_data_handling", "data_residency", "transparency"],
    "legal": ["licence_terms", "exit_options", "transparency", "contestability"],
    "legal_contestability": ["contestability", "transparency", "licence_terms", "exit_options"],
    "fairness": ["fairness", "critic_review", "plain_language"],
    "enterprise_architecture": ["vendor_lock_in", "update_practices", "exit_options", "cost"],
    "arabic_qa": ["arabic_msa", "arabic_gulf", "name_transliteration", "english", "plain_language"],
    "accessibility": ["accessibility", "plain_language", "contestability"],
}
# Provider evidence field -> the check it bears on (so an evidence-gap concern finds its owner).
EVIDENCE_AREA = {
    "model_card": "transparency", "intended_use": "licence_terms", "licence_terms": "licence_terms",
    "benchmark_general": "task_accuracy", "benchmark_arabic": "arabic_msa", "safety_evaluation": "prompt_injection",
    "fairness_evaluation": "fairness", "training_data_summary": "transparency", "update_policy": "update_practices",
    "version_pinning": "update_practices", "data_residency": "data_residency", "data_retention": "sensitive_data_handling",
    "security_certifications": "sensitive_data_handling", "pricing": "cost", "exit_terms": "exit_options",
    "incident_disclosure": "update_practices",
}
# How many reviewers each track gets. None = every reviewer in the department.
REVIEWERS_PER_TRACK = {"fast": 2, "standard": 3, "full": None}
DECISIONS = ("approved", "approved_with_conditions", "rejected")
_FLAGGED = ("failed", "warning", "error")
_SEVERITY_RANK = {"low": 0, "medium": 1, "high": 2}

# Known limits of this prototype. They are true of every assessment until fixed, so the record says so.
STANDING_LIMITATIONS = [
    "Test sets are small (3 to 8 cases per check): one wrong answer can move a score by 0.1 or more.",
    "The Arabic and Gulf-dialect test cases are synthetic and have not yet been reviewed by a native speaker.",
    "The compliance checklist is a synthetic paraphrase of UAE requirements and has not been validated by a legal officer.",
]


def check_area(area: str | None) -> str | None:
    """'evidence:data_retention' -> 'sensitive_data_handling'; a check key stays as it is."""
    if not area:
        return None
    if area.startswith("evidence:"):
        return EVIDENCE_AREA.get(area.split(":", 1)[1])
    return area if area in catalog.CHECKS else None


# ───────────── loading ─────────────

async def load(session: AsyncSession, assessment_id: int) -> Assessment:
    assessment = await session.get(Assessment, assessment_id)
    if assessment is None:
        raise HTTPException(404, "No such assessment")
    return assessment


async def department_people(session: AsyncSession, department_id: int) -> tuple[list[User], User]:
    """(reviewers, named approver) of a department."""
    people = (await session.execute(select(User).where(User.department_id == department_id).order_by(User.id))).scalars().all()
    reviewers = [u for u in people if u.role == "reviewer" and u.reviewer_role]
    approver = next((u for u in people if u.can_approve), None)
    if approver is None:
        raise HTTPException(409, "This department has no named approver; nobody can be accountable for the decision.")
    return reviewers, approver


async def _checks(session: AsyncSession, assessment_id: int) -> list[CheckResult]:
    return list((await session.execute(select(CheckResult).where(CheckResult.assessment_id == assessment_id)
                                       .order_by(CheckResult.id))).scalars())


async def _concerns(session: AsyncSession, assessment_id: int) -> list[Concern]:
    return list((await session.execute(select(Concern).where(Concern.assessment_id == assessment_id)
                                       .order_by(Concern.id))).scalars())


async def _current_reviews(session: AsyncSession, assessment: Assessment) -> list[Review]:
    current = (await session.execute(select(func.max(Review.round)).where(Review.assessment_id == assessment.id))).scalar()
    if current is None:
        return []
    return list((await session.execute(select(Review).where(Review.assessment_id == assessment.id, Review.round == current)
                                       .order_by(Review.id))).scalars())


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_status(assessment: Assessment, *allowed: str) -> None:
    if assessment.status not in allowed:
        raise HTTPException(409, f"This step needs the assessment to be {' or '.join(repr(s) for s in allowed)}; it is '{assessment.status}'.")


def _require_department(user: User, assessment: Assessment, what: str) -> None:
    if user.department_id != assessment.department_id:
        raise HTTPException(403, f"Only the department that owns the assessment can {what}; accountability stays with that department.")


def _require_approver(user: User, assessment: Assessment, what: str) -> None:
    if not (user.can_approve and user.department_id == assessment.department_id):
        raise HTTPException(403, f"Only the owning department's named approver can {what}.")


# ───────────── Agent 6: recommendation (plain rules) ─────────────

def recommend(checks: list[CheckResult], conditions: list[dict]) -> dict:
    """Any failed check -> do not approve. Warnings or conditions -> approve with conditions. Otherwise approve.

    This is advice to the approver. It is never written as a decision.
    """
    failed = sorted(c.check_key for c in checks if c.status in ("failed", "error"))
    warnings = sorted(c.check_key for c in checks if c.status == "warning")
    reasons = []
    if failed:
        value = "reject"
        reasons.append({"rule": "G1", "reason": "At least one check failed or could not be completed: "
                                                + ", ".join(catalog.CHECKS[c][1] for c in failed) + ". Do not approve."})
    elif warnings or conditions:
        value = "approve_with_conditions"
        if warnings:
            reasons.append({"rule": "G2", "reason": "Every check passed, but these pass only with conditions: "
                                                    + ", ".join(catalog.CHECKS[c][1] for c in warnings) + "."})
        if conditions:
            reasons.append({"rule": "G3", "reason": f"{len(conditions)} deployment condition(s) were suggested by the checks or inherited from reused evidence."})
    else:
        value = "approve"
        reasons.append({"rule": "G4", "reason": "Every required check passed and no condition was suggested."})
    return {"value": value, "reasons": reasons, "failed_checks": failed, "warning_checks": warnings}


# ───────────── Agent 6: choosing reviewers ─────────────

def choose_reviewers(reviewers: list[User], use_case: UseCase, track: str, required: list[str],
                     checks: list[CheckResult], concerns: list[Concern]) -> tuple[list[dict], list[dict]]:
    """Rank the department's reviewers by how much of this assessment falls in their area. Returns (chosen, not chosen)."""
    status = {c.check_key: c.status for c in checks}
    concern_areas = [check_area(c.area) for c in concerns if c.status == "open"]
    personal = use_case.data_sensitivity in ("personal", "sensitive_personal")
    arabic = any(lang.startswith("ar") for lang in use_case.languages)
    ranked = []
    for person in reviewers:
        role = person.reviewer_role
        covered = [c for c in ROLE_AREAS.get(role, []) if c in required]
        flagged = [c for c in covered if status.get(c) in _FLAGGED]
        open_concerns = sum(1 for area in concern_areas if area in ROLE_AREAS.get(role, []))
        score = 10 * len(flagged) + 4 * open_concerns + 3 * len(covered)
        why = []
        if role == "business_owner":
            score += 1000
            why.append("Business owner: always reviews, because the service and its outcome belong to them.")
        bonus = [(role in ("security", "data_protection") and personal, "personal data is processed"),
                 (role in ("legal", "legal_contestability") and use_case.audience_type == "citizen_facing", "the public uses it directly"),
                 (role == "accessibility" and (use_case.vulnerable_users or use_case.audience_type == "citizen_facing"), "affected people include vulnerable users or the public"),
                 (role == "arabic_qa" and arabic, "the service works in Arabic")]
        for applies, reason in bonus:
            if applies:
                score += 5
                why.append(f"Relevant because {reason}.")
        if covered:
            why.append(f"Responsible for: {', '.join(catalog.CHECKS[c][1] for c in covered)}.")
        if flagged:
            why.append(f"Needs their judgement on: {', '.join(catalog.CHECKS[c][1] + ' (' + status[c] + ')' for c in flagged)}.")
        if open_concerns:
            why.append(f"{open_concerns} open concern(s) fall in their area.")
        ranked.append({"user": person, "score": score, "covered": covered, "why": " ".join(why) or "No checks in their area on this track."})
    ranked.sort(key=lambda r: (-r["score"], r["user"].id))
    limit = REVIEWERS_PER_TRACK[track]
    chosen = ranked if limit is None else ranked[:limit]
    left_out = [] if limit is None else ranked[limit:]
    for entry in left_out:
        entry["why"] = f"Not needed on the {track} track ({limit} reviewers): less of this assessment falls in their area. " + entry["why"]
    return chosen, left_out


def route_concern(concern: Concern, reviews: list[Review], approver: User) -> int:
    """The reviewer responsible for a concern's area; otherwise the business owner; otherwise the approver."""
    area = check_area(concern.area)
    for review in reviews:
        if area and area in ROLE_AREAS.get(review.reviewer_role, []):
            return review.reviewer_id
    owner = next((r for r in reviews if r.reviewer_role == "business_owner"), None)
    return owner.reviewer_id if owner else approver.id


# ───────────── Agent 6: the decision record (Assurance Package) ─────────────

class PlainSummary(BaseModel):
    summary: str = Field(min_length=40, max_length=1500, description="Plain-language summary for a non-technical approver")


def _residual_risk(concerns: list[Concern], checks: list[CheckResult]) -> dict:
    remaining = [c for c in concerns if c.status in ("open", "accepted_as_residual_risk")]
    warnings = [c for c in checks if c.status == "warning"]
    top = max((_SEVERITY_RANK[c.severity] for c in remaining), default=-1)
    level = "high" if top == 2 else "medium" if top == 1 or warnings else "low"
    items = [{"concern_id": c.id, "title": c.title, "severity": c.severity, "status": c.status} for c in remaining]
    items += [{"check": c.check_key, "title": catalog.CHECKS[c.check_key][1], "status": "warning",
               "note": (c.details or {}).get("note", "")} for c in warnings]
    return {"level": level, "items": items}


async def build_record(session: AsyncSession, assessment: Assessment, *, decision: Approval | None = None) -> DecisionRecord:
    """Rule-built content plus an LLM-drafted plain summary. Each call adds a new version; old versions are kept."""
    started = time.perf_counter()
    use_case = await session.get(UseCase, assessment.use_case_id)
    version = await session.get(ModelVersion, assessment.model_version_id)
    model = await session.get(AIModel, version.model_id)
    department = await session.get(Department, assessment.department_id)
    reviewers, approver = await department_people(session, assessment.department_id)
    checks = await _checks(session, assessment.id)
    concerns = await _concerns(session, assessment.id)
    reviews = await _current_reviews(session, assessment)
    people = {u.id: u for u in (await session.execute(select(User))).scalars()}
    findings = (await session.execute(
        select(ComplianceFinding, ComplianceRule).join(ComplianceRule, ComplianceRule.id == ComplianceFinding.rule_id)
        .where(ComplianceFinding.assessment_id == assessment.id).order_by(ComplianceRule.id))).all()
    evaluation = assessment.summary.get("evaluation", {})
    evidence = assessment.summary.get("evidence", {})
    conditions = evaluation.get("suggested_conditions", [])
    recommendation = assessment.summary.get("recommendation") or recommend(checks, conditions)
    plan = assessment.plan or {}

    assumptions = [
        f"Used by: {use_case.audience_type.replace('_', '-')}. People affected: {', '.join(use_case.affected_users)}.",
        f"The AI's authority is '{use_case.autonomy_level.replace('_', ' ')}' and human oversight is '{use_case.human_oversight.replace('_', ' ')}'.",
        f"The most sensitive data it handles is '{use_case.data_sensitivity.replace('_', ' ')}'.",
        f"Model {model.name} version {version.version} is used exactly as assessed; any provider update triggers reassessment.",
    ]
    if use_case.expected_volume:
        assumptions.append(f"Expected volume: {use_case.expected_volume}.")
    if plan.get("source"):
        assumptions.append(f"Evidence reused from {plan['source']['reference']} still holds: same model version, checked against this card's own thresholds.")
    if evidence.get("counts", {}).get("claimed"):
        assumptions.append(f"{evidence['counts']['claimed']} provider evidence field(s) are the provider's own claim and were not independently checked.")

    limitations = [f"Not tested: {catalog.CHECKS[d['check']][1]}. {d['reason']}" for d in plan.get("dropped_checks", [])]
    reused = [c for c in checks if c.source == "reused"]
    if reused:
        limitations.append(f"{len(reused)} check(s) were reused from earlier assessments and not re-run here: "
                           + ", ".join(catalog.CHECKS[c.check_key][1] for c in reused) + ".")
        origins = {c.reused_from_assessment_id for c in reused if c.reused_from_assessment_id}
        seeded = (await session.execute(select(Assessment.reference).where(Assessment.id.in_(origins), Assessment.is_history.is_(True))
                                        .order_by(Assessment.id))).scalars().all() if origins else []
        if seeded:
            limitations.insert(0, f"Reused scores come from seeded example history ({', '.join(seeded)}): they were written for the "
                                  "demonstration, not measured on the model. Run the checks fresh before relying on them.")
    for gap in evidence.get("gaps", []):
        if gap["severity"] != "low":
            limitations.append(f"Provider evidence {gap['status']}: {gap['title']}. {gap['risk']}")
    if evaluation.get("llm", {}).get("mode") == "mock":
        limitations.insert(0, "Scores come from mock mode (LLM_MODE=mock), not from the real model. They say nothing about how the model performs.")
    limitations += STANDING_LIMITATIONS

    # Real open data the evaluation used: which published tables, which version, and how the model did on them.
    from app.services import opendata
    open_runs = (await session.execute(select(TestRun, TestCase).join(TestCase, TestCase.id == TestRun.test_case_id)
                                       .where(TestRun.assessment_id == assessment.id, TestCase.origin == "bayanat"))).all()
    data_sources = []
    for ds in await opendata.sources_of(session, use_case.id):
        mine = [(run, case) for run, case in open_runs if case.meta.get("data_source_id") == ds.id]
        data_sources.append({"key": ds.key, "title": ds.title, "publisher": ds.publisher, "portal": ds.portal, "page_url": ds.page_url,
                             "licence_url": ds.licence_url, "last_updated": ds.last_updated.isoformat() if ds.last_updated else None,
                             "version": ds.checksum[:12], "cases_run": len(mine),
                             "cases_passed": sum(run.passed is True for run, _ in mine)})
    if data_sources and not open_runs:
        limitations.append("The open-data test cases for this use case were not run here: the checks they belong to were reused from an earlier assessment.")

    content = {
        "reference": assessment.reference,
        "use_case": {"code": use_case.code, "title": use_case.title, "purpose": use_case.purpose},
        "model": f"{model.name} {version.version}", "provider": model.provider,
        "risk_tier": assessment.risk_tier, "track": assessment.track, "tier_rules": assessment.tier_rationale,
        "recommendation": recommendation,
        "assumptions": assumptions,
        "limitations": limitations,
        "evidence_used": {
            "checks": [{"check": c.check_key, "title": catalog.CHECKS[c.check_key][1], "status": c.status, "score": c.score,
                        "threshold": c.threshold, "source": c.source, "reused_from_assessment_id": c.reused_from_assessment_id,
                        "note": (c.details or {}).get("note", "")} for c in checks],
            "compliance": [{"rule": rule.code, "title": rule.title, "status": finding.status, "evidence_refs": finding.evidence_refs}
                           for finding, rule in findings],
            "provider_evidence": evidence.get("counts", {}),
            "reuse_source": plan.get("source"),
            "open_data": data_sources,
        },
        "conditions": conditions,
        "concerns": [{"id": c.id, "title": c.title, "severity": c.severity, "status": c.status,
                      "raised_by": people[c.raised_by_id].full_name if c.raised_by_id else c.raised_by_agent,
                      "assigned_to": people[c.assigned_to_id].full_name if c.assigned_to_id else None,
                      "resolution": c.resolution} for c in concerns],
        "residual_risk": _residual_risk(concerns, checks),
        "reviewers": [{"name": people[r.reviewer_id].full_name, "role": catalog.REVIEWER_ROLES.get(r.reviewer_role, r.reviewer_role),
                       "status": r.status, "comment": r.comment} for r in reviews],
        "accountable_owner": {"name": approver.full_name, "title": approver.title, "department": department.name},
        "decision": None,
    }
    if decision is not None:
        content["decision"] = {
            "decision": decision.decision, "by": approver.full_name if decision.approver_id == approver.id else people[decision.approver_id].full_name,
            "reason": decision.reason, "conditions": decision.conditions,
            "risk_accepted_by": people[decision.risk_accepted_by_id].full_name if decision.risk_accepted_by_id else None,
            "decided_at": decision.decided_at.isoformat() if decision.decided_at else _now().isoformat(),
        }

    def mock_summary() -> PlainSummary:
        rec = recommendation["value"].replace("_", " ")
        flagged = recommendation["failed_checks"] + recommendation["warning_checks"]
        text = (f"{department.name} wants to use {model.name} {version.version} for '{use_case.title}'. "
                f"It is rated {assessment.risk_tier} risk, so it went through the {assessment.track} track. "
                f"{sum(c.status == 'passed' for c in checks)} of {len(checks)} checks passed"
                + (f"; these need attention: {', '.join(catalog.CHECKS[c][1] for c in flagged)}" if flagged else "") + ". "
                f"The system recommends: {rec}. "
                + (f"It would run under {len(conditions)} condition(s). " if conditions else "")
                + f"Residual risk is {content['residual_risk']['level']}.")
        return PlainSummary(summary=text)

    try:
        drafted = await llm.call_json(
            agent=ORCHESTRATOR, step="draft_plain_summary", assessment_id=assessment.id, schema=PlainSummary,
            system=("Write a short plain-language summary (at most 150 words) of this AI assessment for a senior official who is not "
                    "technical. Say what the AI would do, the risk tier, what passed, what needs attention, the conditions, and the "
                    "system's recommendation. Use only the facts given. Do not say the system approved anything: a named person decides."),
            user=str({k: content[k] for k in ("use_case", "model", "risk_tier", "track", "recommendation", "conditions", "residual_risk")}
                     | {"checks": [(c["title"], c["status"]) for c in content["evidence_used"]["checks"]]})[:12000],
            mock=mock_summary)
        summary = drafted.summary
    except llm.LLMFailure:
        summary = mock_summary().summary + " (Automatic summary: the drafting model gave no valid output.)"
    # Added by code, never by the model: who decides.
    if decision is None:
        summary += f" This is a recommendation only. The decision belongs to {approver.full_name}, {approver.title}."
    else:
        summary += f" Decision: {decision.decision.replace('_', ' ')} by {content['decision']['by']}."

    latest = (await session.execute(select(func.max(DecisionRecord.version)).where(DecisionRecord.assessment_id == assessment.id))).scalar() or 0
    record = DecisionRecord(assessment_id=assessment.id, version=latest + 1, content=content, plain_summary=summary)
    session.add(record)
    session.add(StepTiming(assessment_id=assessment.id, step_key="decision_record", mode="automated",
                           duration_seconds=round(time.perf_counter() - started, 4)))
    session.add(audit_entry("decision_record.built", agent=ORCHESTRATOR, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id, details={"version": record.version, "recommendation": recommendation["value"],
                                                                  "for_decision": decision is not None}))
    await session.flush()
    return record


# ───────────── Agent 6: sending the reviews ─────────────

async def submit_for_review(session: AsyncSession, assessment: Assessment, user: User) -> dict:
    """Recommendation, reviewers chosen and notified at the same time, concerns routed, decision record v-next."""
    _require_department(user, assessment, "send it for review")
    _require_status(assessment, "evaluated")
    use_case = await session.get(UseCase, assessment.use_case_id)
    reviewers, approver = await department_people(session, assessment.department_id)
    checks = await _checks(session, assessment.id)
    concerns = await _concerns(session, assessment.id)
    conditions = assessment.summary.get("evaluation", {}).get("suggested_conditions", [])

    recommendation = recommend(checks, conditions)
    assessment.recommendation = recommendation["value"]

    chosen, left_out = choose_reviewers(reviewers, use_case, assessment.track, assessment.plan.get("required_checks", []), checks, concerns)
    previous = (await session.execute(select(func.max(Review.round)).where(Review.assessment_id == assessment.id))).scalar() or 0
    sent_at = _now()
    reviews = []
    for entry in chosen:  # all at once: no review waits for another
        review = Review(assessment_id=assessment.id, reviewer_id=entry["user"].id, reviewer_role=entry["user"].reviewer_role,
                        round=previous + 1, responsibilities=entry["covered"], selection_reason=entry["why"],
                        status="pending", assigned_at=sent_at)
        session.add(review)
        reviews.append(review)
    await session.flush()

    routed = []
    for concern in concerns:
        if concern.status == "open" and concern.raised_by_id is None:  # agent concerns go to whoever owns the area this round
            concern.assigned_to_id = route_concern(concern, reviews, approver)
            routed.append({"concern_id": concern.id, "assigned_to_id": concern.assigned_to_id})

    assessment.summary = {**assessment.summary, "recommendation": recommendation, "governance": {
        "round": previous + 1, "review_started_at": sent_at.isoformat(), "approver_id": approver.id,
        "reviewers": [{"user_id": e["user"].id, "name": e["user"].full_name, "role": e["user"].reviewer_role, "why": e["why"]} for e in chosen],
        "not_selected": [{"user_id": e["user"].id, "name": e["user"].full_name, "role": e["user"].reviewer_role, "why": e["why"]} for e in left_out],
    }}
    assessment.status = "in_review"
    record = await build_record(session, assessment)
    session.add(audit_entry("governance.recommended", agent=ORCHESTRATOR, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id, details=recommendation))
    session.add(audit_entry("reviews.assigned", agent=ORCHESTRATOR, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id,
                            details={"round": previous + 1, "sent_at": sent_at.isoformat(), "track": assessment.track,
                                     "reviewers": [{"name": e["user"].full_name, "role": e["user"].reviewer_role} for e in chosen],
                                     "concerns_routed": routed, "requested_by": user.full_name}))
    await session.commit()
    return {"recommendation": recommendation, "reviews": [r.id for r in reviews], "decision_record_version": record.version}


# ───────────── reviewers ─────────────

async def respond(session: AsyncSession, review: Review, user: User, status: str, comment: str, new_concerns: list[dict]) -> Assessment:
    if review.reviewer_id != user.id:
        raise HTTPException(403, "Only the reviewer this review was assigned to can answer it.")
    assessment = await load(session, review.assessment_id)
    _require_status(assessment, "in_review")
    if review.status != "pending":
        raise HTTPException(409, f"This review was already answered ('{review.status}').")
    if status == "no_objection" and new_concerns:
        raise HTTPException(422, "A review with concerns must have status 'concerns' or 'objection'.")
    review.status, review.comment, review.submitted_at = status, comment, _now()
    if status != "no_objection" and not new_concerns:
        # An objection or concern is always tracked as a concern, so it cannot be lost.
        new_concerns = [{"title": f"{catalog.REVIEWER_ROLES.get(review.reviewer_role, review.reviewer_role)}: {comment[:150]}",
                         "detail": comment, "severity": "high" if status == "objection" else "medium", "area": None}]
    for item in new_concerns:
        severity = item["severity"]
        if status == "objection":
            severity = "high"  # an objection blocks approval until it is resolved or the risk is accepted
        area = item.get("area") or (review.responsibilities[0] if review.responsibilities else None)
        session.add(Concern(assessment_id=assessment.id, raised_by_id=user.id, title=item["title"], detail=item.get("detail", ""),
                            severity=severity, area=area, assigned_to_id=user.id))
    session.add(audit_entry("review.submitted", user=user, entity_type="review", entity_id=review.id, assessment_id=assessment.id,
                            details={"status": status, "role": review.reviewer_role, "concerns_raised": len(new_concerns)}))
    await session.flush()
    await _maybe_ready_for_decision(session, assessment)
    await session.commit()
    return assessment


async def _maybe_ready_for_decision(session: AsyncSession, assessment: Assessment) -> None:
    reviews = await _current_reviews(session, assessment)
    if not reviews or any(r.status == "pending" for r in reviews):
        return
    started = min(r.assigned_at for r in reviews)
    finished = max(r.submitted_at for r in reviews)
    # Parallel reviews: elapsed time is the slowest reviewer, not the sum of all of them.
    session.add(StepTiming(assessment_id=assessment.id, step_key="review", mode="human",
                           duration_seconds=round((finished - started).total_seconds(), 3), started_at=started))
    assessment.status = "awaiting_decision"
    assessment.summary = {**assessment.summary, "governance": {
        **assessment.summary.get("governance", {}), "awaiting_decision_since": finished.isoformat(),
        "sum_of_review_durations_s": round(sum((r.submitted_at - r.assigned_at).total_seconds() for r in reviews), 3),
        "review_elapsed_s": round((finished - started).total_seconds(), 3)}}
    await build_record(session, assessment)
    session.add(audit_entry("reviews.completed", agent=ORCHESTRATOR, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id, details={"statuses": {r.reviewer_role: r.status for r in reviews}}))


async def raise_concern(session: AsyncSession, assessment: Assessment, user: User, item: dict) -> Concern:
    _require_status(assessment, "in_review", "awaiting_decision")
    reviews = await _current_reviews(session, assessment)
    if user.id not in {r.reviewer_id for r in reviews} and not (user.can_approve and user.department_id == assessment.department_id):
        raise HTTPException(403, "Only a reviewer of this assessment or the department's approver can raise a concern on it.")
    concern = Concern(assessment_id=assessment.id, raised_by_id=user.id, title=item["title"], detail=item.get("detail", ""),
                      severity=item["severity"], area=item.get("area"), assigned_to_id=user.id)
    session.add(concern)
    await session.flush()
    session.add(audit_entry("concern.raised", user=user, entity_type="concern", entity_id=concern.id, assessment_id=assessment.id,
                            details={"title": concern.title, "severity": concern.severity}))
    await session.commit()
    return concern


async def close_concern(session: AsyncSession, concern: Concern, user: User, text: str, *, accept_risk: bool) -> Concern:
    assessment = await load(session, concern.assessment_id)
    _require_status(assessment, "in_review", "awaiting_decision")
    if concern.status != "open":
        raise HTTPException(409, f"This concern is already '{concern.status}'.")
    if accept_risk:
        _require_approver(user, assessment, "accept a concern as residual risk")
        concern.status = "accepted_as_residual_risk"
    else:
        allowed = {concern.assigned_to_id, concern.raised_by_id}
        if user.id not in allowed and not (user.can_approve and user.department_id == assessment.department_id):
            raise HTTPException(403, "Only the person responsible for this concern, the person who raised it, or the department's approver can resolve it.")
        concern.status = "resolved"
    concern.resolution, concern.resolved_by_id, concern.resolved_at = text, user.id, _now()
    session.add(audit_entry("concern.risk_accepted" if accept_risk else "concern.resolved", user=user, entity_type="concern",
                            entity_id=concern.id, assessment_id=assessment.id,
                            details={"title": concern.title, "severity": concern.severity, "text": text}))
    await session.commit()
    return concern


# ───────────── Agent 7: the human decision ─────────────

async def send_back(session: AsyncSession, assessment: Assessment, user: User, reason: str) -> Assessment:
    """The approver returns the assessment for re-evaluation. Pending reviews are withdrawn; a new round follows."""
    _require_approver(user, assessment, "send an assessment back")
    _require_status(assessment, "in_review", "awaiting_decision")
    for review in await _current_reviews(session, assessment):
        if review.status == "pending":
            review.status, review.submitted_at = "withdrawn", _now()
    assessment.status = "sent_back"
    assessment.summary = {**assessment.summary, "sent_back": {"by": user.full_name, "reason": reason, "at": _now().isoformat()}}
    session.add(audit_entry("assessment.sent_back", user=user, entity_type="assessment", entity_id=assessment.id,
                            assessment_id=assessment.id, details={"reason": reason}))
    await session.commit()
    return assessment


async def decide(session: AsyncSession, assessment: Assessment, user: User, *, decision: str, reason: str,
                 conditions: list[str] | None, risk_accepted_by_email: str | None, override_recommendation: bool) -> Approval:
    _require_approver(user, assessment, "decide")
    _require_status(assessment, "awaiting_decision")
    if decision not in DECISIONS:
        raise HTTPException(422, f"decision must be one of {DECISIONS}")
    concerns = await _concerns(session, assessment.id)
    blocking = [c for c in concerns if c.status == "open" and c.severity == "high"]
    if blocking and decision != "rejected":
        raise HTTPException(409, {"message": "Open high-severity concerns must be resolved or accepted as residual risk before approval.",
                                  "open_high_concerns": [{"id": c.id, "title": c.title} for c in blocking]})
    if assessment.recommendation == "reject" and decision != "rejected" and not override_recommendation:
        raise HTTPException(409, "The system recommends not approving (a check failed). To approve anyway, set "
                                 "override_recommendation=true and explain why in the reason. The override is recorded.")

    suggested = [c["condition"] for c in assessment.summary.get("evaluation", {}).get("suggested_conditions", [])]
    if decision == "approved_with_conditions":
        final_conditions = conditions if conditions is not None else suggested
        if not final_conditions:
            raise HTTPException(422, "Approve with conditions needs at least one condition.")
    elif decision == "approved":
        if conditions:
            raise HTTPException(422, "An approval without conditions cannot carry conditions; use approved_with_conditions.")
        final_conditions = []
    else:
        final_conditions = []

    risk_owner = None
    if decision != "rejected":
        risk_owner = user
        if risk_accepted_by_email:
            risk_owner = (await session.execute(select(User).where(User.email == risk_accepted_by_email.lower()))).scalar_one_or_none()
            if risk_owner is None or risk_owner.department_id != assessment.department_id or risk_owner.role != "reviewer":
                raise HTTPException(422, "The person accepting the residual risk must be a senior reviewer in the owning department.")

    now = _now()
    approval = Approval(assessment_id=assessment.id, decision=decision, approver_id=user.id,
                        risk_accepted_by_id=risk_owner.id if risk_owner else None, reason=reason,
                        conditions=final_conditions, decided_at=now)
    session.add(approval)
    assessment.status, assessment.completed_at = decision, now
    waiting_since = assessment.summary.get("governance", {}).get("awaiting_decision_since")
    if waiting_since:
        session.add(StepTiming(assessment_id=assessment.id, step_key="approval", mode="human", started_at=datetime.fromisoformat(waiting_since),
                               duration_seconds=round((now - datetime.fromisoformat(waiting_since)).total_seconds(), 3)))
    await session.flush()

    deployment = None
    if decision != "rejected":
        deployment = await create_deployment(session, assessment, approval)
    await build_record(session, assessment, decision=approval)
    session.add(audit_entry("decision.recorded", user=user, entity_type="assessment", entity_id=assessment.id, assessment_id=assessment.id,
                            details={"decision": decision, "reason": reason, "conditions": final_conditions,
                                     "system_recommendation": assessment.recommendation,
                                     "overrode_recommendation": assessment.recommendation == "reject" and decision != "rejected",
                                     "conditions_dropped": [c for c in suggested if c not in final_conditions],
                                     "risk_accepted_by": risk_owner.full_name if risk_owner else None,
                                     "deployment_id": deployment.id if deployment else None}))

    if assessment.reassessment_of_deployment_id:
        from app.services import lifecycle  # local import: lifecycle imports this module
        await lifecycle.on_reassessment_decided(session, assessment, approval, deployment, user)
    await session.commit()
    return approval


async def create_deployment(session: AsyncSession, assessment: Assessment, approval: Approval) -> Deployment:
    """The model goes live carrying the approval's conditions; those conditions are what Agent 8 monitors."""
    findings = (await session.execute(select(ComplianceFinding).where(ComplianceFinding.assessment_id == assessment.id))).scalars().all()
    statuses = {f.status for f in findings}
    if "non_compliant" in statuses:
        compliance, note = "non_compliant", "Approved although at least one compliance rule is not met (recorded as an override)."
    elif "unknown" in statuses or ("conditional" in statuses and not approval.conditions):
        compliance, note = "at_risk", "Some rules are only met under conditions or rest on missing evidence."
    else:
        compliance, note = "compliant", "Every applicable rule is met, conditional rules through the approval's conditions."
    deployment = Deployment(
        assessment_id=assessment.id, department_id=assessment.department_id, use_case_id=assessment.use_case_id,
        model_version_id=assessment.model_version_id, status="active", conditions=approval.conditions,
        condition_status=[{"condition": c, "status": "unverified", "checked_at": None, "checked_by": None, "note": ""}
                          for c in approval.conditions],
        compliance_status=compliance, compliance_note=note, deployed_at=approval.decided_at,
        next_review_due=approval.decided_at + timedelta(days=90))
    session.add(deployment)
    await session.flush()
    session.add(audit_entry("deployment.created", agent=APPROVAL_GATE, entity_type="deployment", entity_id=deployment.id,
                            assessment_id=assessment.id,
                            details={"conditions": approval.conditions, "compliance_status": compliance,
                                     "next_review_due": deployment.next_review_due.isoformat()}))
    return deployment
