"""Agent 8, Lifecycle Monitor. Plain rules, no LLM.

Triggers: new model version, provider terms change, data source change, more autonomy, new service
context, incident, complaint spike, performance drift, condition breach and the quarterly standards check.
Each trigger is recorded as a monitor event, alerts every department using the affected model, and
where needed sends the deployment back for reassessment.

Exit rules say when to pause, replace or retire. The monitor pauses on its own only to protect people
(an open high-severity incident, a blocker rule no longer met, a large performance drop). Resuming,
retiring and replacing are always a named human's decision.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog
from app.audit import audit_entry
from app.models import (
    AIModel, Alert, Approval, Assessment, Deployment, Feedback, Incident, Lesson, ModelVersion, MonitorEvent,
    ProviderEvidence, UseCase, User,
)
from app.services import compliance as compliance_rules

MONITOR = "lifecycle_monitor"
LIVE = ("active", "under_reassessment", "paused")
COMPLAINT_SOURCES = ("citizen_complaint", "appeal")
# Complaint spike: at least SPIKE_MIN_COUNT complaints/appeals in the last SPIKE_WINDOW_DAYS, and a daily rate at least
# SPIKE_RATIO times the rate of the BASELINE_DAYS before that.
SPIKE_WINDOW_DAYS, BASELINE_DAYS, SPIKE_MIN_COUNT, SPIKE_RATIO = 14, 90, 5, 2.0
DRIFT_PAUSE_MARGIN = 0.10  # pause when observed performance is this far below the threshold
PAUSED_TOO_LONG_DAYS = 90
REVIEW_INTERVAL_DAYS = 90

EXIT_RULES = {
    "X1": ("pause", "An open high-severity incident: pause until it is resolved and a named person resumes the service."),
    "X2": ("pause", "A blocker compliance rule is no longer met."),
    "X3": ("pause", f"Observed performance is more than {DRIFT_PAUSE_MARGIN:.2f} below the approved threshold."),
    "X4": ("reassess", "A change since approval (version, terms, data, autonomy, context, complaints, drift, breach) needs re-checking."),
    "X5": ("replace", "The approved version is withdrawn or no longer the provider's current version: reassess on a supported version or replace."),
    "X6": ("retire", "A reassessment was rejected: the deployment cannot continue as it is."),
    "X7": ("retire", f"Paused for more than {PAUSED_TOO_LONG_DAYS} days without being resumed."),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ───────────── events, alerts, status changes ─────────────

async def record_event(session: AsyncSession, trigger_type: str, *, payload: dict, source: str, model_id: int | None = None,
                       version_id: int | None = None, deployment: Deployment | None = None) -> MonitorEvent:
    assert trigger_type in catalog.MONITOR_EVENT_TYPES, trigger_type
    event = MonitorEvent(trigger_type=trigger_type, model_id=model_id, model_version_id=version_id,
                         deployment_id=deployment.id if deployment else None,
                         department_id=deployment.department_id if deployment else None, payload=payload, source=source)
    session.add(event)
    await session.flush()
    session.add(audit_entry("monitor.event", agent=MONITOR, entity_type="monitor_event", entity_id=event.id,
                            details={"trigger_type": trigger_type, "deployment_id": event.deployment_id, **payload}))
    return event


async def alert(session: AsyncSession, event: MonitorEvent, department_id: int, deployment: Deployment | None, *,
                severity: str, title: str, message: str, action: str) -> Alert:
    row = Alert(event_id=event.id, department_id=department_id, deployment_id=deployment.id if deployment else None,
                severity=severity, title=title, message=message, action_required=action)
    session.add(row)
    await session.flush()
    return row


async def set_status(session: AsyncSession, deployment: Deployment, status: str, reason: str, *, user: User | None = None,
                     rule: str | None = None) -> bool:
    """Move a deployment. Never moves a retired one, and never weakens a pause to a reassessment."""
    if deployment.status == "retired" or deployment.status == status:
        return False
    if deployment.status == "paused" and status == "under_reassessment":
        return False
    before = deployment.status
    deployment.status, deployment.status_reason = status, reason
    if status == "retired":
        deployment.retired_at = _now()
    session.add(audit_entry("deployment.status_changed", user=user, agent=None if user else MONITOR, entity_type="deployment",
                            entity_id=deployment.id, assessment_id=deployment.assessment_id,
                            details={"from": before, "to": status, "reason": reason, "exit_rule": rule}))
    return True


async def model_of(session: AsyncSession, deployment: Deployment) -> tuple[AIModel, ModelVersion]:
    version = await session.get(ModelVersion, deployment.model_version_id)
    return await session.get(AIModel, version.model_id), version


async def deployments_of_model(session: AsyncSession, model_id: int) -> list[Deployment]:
    versions = select(ModelVersion.id).where(ModelVersion.model_id == model_id)
    return list((await session.execute(select(Deployment).where(Deployment.model_version_id.in_(versions), Deployment.status.in_(LIVE))
                                       .order_by(Deployment.id))).scalars())


async def _label(session: AsyncSession, deployment: Deployment) -> str:
    use_case = await session.get(UseCase, deployment.use_case_id)
    model, version = await model_of(session, deployment)
    return f"{use_case.title} ({model.name} {version.version})"


async def _send_back(session: AsyncSession, event: MonitorEvent, deployment: Deployment, *, severity: str, title: str,
                     message: str, rule: str = "X4") -> Alert:
    await set_status(session, deployment, "under_reassessment", f"{title}. {message}", rule=rule)
    return await alert(session, event, deployment.department_id, deployment, severity=severity, title=title,
                       message=message + f" Start the reassessment with POST /deployments/{deployment.id}/reassess.", action="reassess")


async def _pause(session: AsyncSession, event: MonitorEvent, deployment: Deployment, rule: str, detail: str) -> Alert:
    await set_status(session, deployment, "paused", f"Exit rule {rule}: {EXIT_RULES[rule][1]} {detail}", rule=rule)
    return await alert(session, event, deployment.department_id, deployment, severity="high",
                       title=f"Paused by exit rule {rule}: {await _label(session, deployment)}",
                       message=f"{EXIT_RULES[rule][1]} {detail} Only the department's named approver can resume it "
                               f"(POST /deployments/{deployment.id}/resume) once the cause is dealt with.", action="pause")


async def _tell_other_users(session: AsyncSession, event: MonitorEvent, model_id: int, except_department: int | None,
                            title: str, message: str) -> list[Alert]:
    """Every other department running the same model hears about it (R4: lessons are shared)."""
    alerts, told = [], set()
    for deployment in await deployments_of_model(session, model_id):
        if deployment.department_id == except_department or deployment.id in told:
            continue
        told.add(deployment.id)
        alerts.append(await alert(session, event, deployment.department_id, deployment, severity="low", title=title,
                                  message=message, action="info"))
    return alerts


# ───────────── triggers ─────────────

def _pinnable(evidence: ProviderEvidence | None) -> bool:
    return bool(evidence and evidence.status in ("verified", "claimed") and (evidence.value or {}).get("pinning_available"))


async def on_new_version(session: AsyncSession, model: AIModel, new_version: ModelVersion, user: User | None) -> dict:
    """Alert every department using the model. A pinned deployment keeps running and must reassess before switching;
    one that cannot be pinned goes back for reassessment now, because the model may change underneath it."""
    event = await record_event(session, "new_model_version", model_id=model.id, version_id=new_version.id, source="model_registry",
                               payload={"model": model.slug, "version": new_version.version, "changelog": new_version.changelog,
                                        "reported_by": user.full_name if user else None})
    alerts = []
    for deployment in await deployments_of_model(session, model.id):
        version = await session.get(ModelVersion, deployment.model_version_id)
        pin = (await session.execute(select(ProviderEvidence).where(ProviderEvidence.model_version_id == version.id,
                                                                    ProviderEvidence.field == "version_pinning"))).scalar_one_or_none()
        label = await _label(session, deployment)
        if _pinnable(pin):
            alerts.append(await alert(session, event, deployment.department_id, deployment, severity="medium",
                                      title=f"New version {model.name} {new_version.version}: {label}",
                                      message=f"Your deployment stays pinned to version {version.version}, which was approved. Evidence does not "
                                              f"carry across versions: assess {new_version.version} before switching "
                                              f"(POST /deployments/{deployment.id}/reassess).", action="reassess"))
        else:
            alerts.append(await _send_back(session, event, deployment, severity="high",
                                           title=f"New version {model.name} {new_version.version} and no version pinning: {label}",
                                           message=f"The provider gives no way to keep version {version.version}, so the model in use may "
                                                   "already have changed. Sent back for reassessment."))
    # Departments with an assessment of this model still in progress are told too: their evidence may be for an old version.
    open_assessments = (await session.execute(select(Assessment).join(ModelVersion, ModelVersion.id == Assessment.model_version_id)
                                              .where(ModelVersion.model_id == model.id, Assessment.model_version_id != new_version.id,
                                                     Assessment.status.in_(("planned", "evaluating", "evaluated", "in_review", "awaiting_decision")))
                                              )).scalars().all()
    for assessment in open_assessments:
        alerts.append(await alert(session, event, assessment.department_id, None, severity="low",
                                  title=f"New version {model.name} {new_version.version} while {assessment.reference} is in progress",
                                  message="Your assessment is for an earlier version. Decide whether to finish it or start again on the new version.",
                                  action="info"))
    return {"event_id": event.id, "alerts": [a.id for a in alerts]}


async def on_reported_change(session: AsyncSession, trigger_type: str, user: User, *, description: str, details: dict,
                             deployment: Deployment | None, model: AIModel | None) -> dict:
    """provider_terms_change (model-wide) or data_source_change / autonomy_increase / new_service_context (one deployment)."""
    if trigger_type == "provider_terms_change":
        event = await record_event(session, trigger_type, model_id=model.id, source=f"user:{user.id}",
                                   payload={"description": description, **details})
        alerts = []
        for item in await deployments_of_model(session, model.id):
            item.compliance_status, item.compliance_note = "at_risk", f"Provider terms changed: {description}"
            alerts.append(await _send_back(session, event, item, severity="high",
                                           title=f"{model.name} provider terms changed: {await _label(session, item)}",
                                           message=f"{description} Compliance and procurement rules must be re-checked against the new terms."))
        return {"event_id": event.id, "alerts": [a.id for a in alerts]}

    model, _ = await model_of(session, deployment)
    event = await record_event(session, trigger_type, model_id=model.id, version_id=deployment.model_version_id, deployment=deployment,
                               source=f"user:{user.id}", payload={"description": description, **details})
    severity = "high" if trigger_type == "autonomy_increase" else "medium"
    what = {"data_source_change": "The data the service uses has changed",
            "autonomy_increase": "The AI is being given more authority than was approved",
            "new_service_context": "The service is being used in a context it was not assessed for"}[trigger_type]
    sent = await _send_back(session, event, deployment, severity=severity, title=f"{what}: {await _label(session, deployment)}",
                            message=f"{description} The Use-Case Card may need updating before the reassessment.")
    return {"event_id": event.id, "alerts": [sent.id]}


async def on_data_source_updated(session: AsyncSession, ds, change: dict) -> dict:
    """A published table the service relies on has a new version (trigger `data_source_change`).

    New content: every live deployment of a linked use case goes back for reassessment, and departments with an
    assessment in progress are told. Only the date changed: recorded and announced, nothing is sent back.
    """
    from app.services.opendata import linked_use_cases

    use_cases = await linked_use_cases(session, ds.id)
    event = await record_event(session, "data_source_change", source=MONITOR,
                               payload={"data_source": ds.key, "title": ds.title, "publisher": ds.publisher,
                                        "content_changed": change["content_changed"], "before": change["before"],
                                        "after": change["after"], "use_cases": [u.code for u in use_cases]})
    alerts = []
    ids = [u.id for u in use_cases]
    deployments = list((await session.execute(select(Deployment).where(Deployment.use_case_id.in_(ids), Deployment.status.in_(LIVE))
                                              .order_by(Deployment.id))).scalars()) if ids else []
    what = f"'{ds.title}' ({ds.publisher}) was updated on the portal"
    for deployment in deployments:
        if change["content_changed"]:
            alerts.append(await _send_back(session, event, deployment, severity="medium",
                                           title=f"Data source changed: {await _label(session, deployment)}",
                                           message=f"{what}: {change['before']['rows']} rows before, {change['after']['rows']} now. "
                                                   "The open-data test cases were rewritten from the new version."))
        else:
            alerts.append(await alert(session, event, deployment.department_id, deployment, severity="low",
                                      title=f"Data source re-dated, content unchanged: {ds.title}",
                                      message=f"{what}, but the table is identical to the version you were assessed on.", action="info"))
    if ids and change["content_changed"]:
        running = (await session.execute(select(Assessment).where(
            Assessment.use_case_id.in_(ids),
            Assessment.status.in_(("planned", "evaluating", "evaluated", "in_review", "awaiting_decision"))))).scalars().all()
        for assessment in running:
            alerts.append(await alert(session, event, assessment.department_id, None, severity="low",
                                      title=f"Data source changed while {assessment.reference} is in progress",
                                      message=f"{what}. Evaluations already run used the earlier version.", action="info"))
    return {"event_id": event.id, "alerts": [a.id for a in alerts], "deployments_sent_back":
            [d.id for d in deployments] if change["content_changed"] else []}


async def report_incident(session: AsyncSession, user: User, deployment: Deployment, *, title: str, description: str,
                          category: str, severity: str) -> Incident:
    if user.department_id != deployment.department_id:
        raise HTTPException(403, "Incidents are reported by the department running the deployment.")
    model, version = await model_of(session, deployment)
    incident = Incident(deployment_id=deployment.id, department_id=deployment.department_id, model_version_id=version.id,
                        title=title, description=description, category=category, severity=severity, status="open",
                        reported_by_id=user.id)
    session.add(incident)
    await session.flush()
    event = await record_event(session, "incident", model_id=model.id, version_id=version.id, deployment=deployment,
                               source=f"user:{user.id}", payload={"incident_id": incident.id, "title": title, "severity": severity,
                                                                  "category": category})
    if severity == "high":
        await _pause(session, event, deployment, "X1", f"Incident: {title}.")
    elif severity == "medium":
        await _send_back(session, event, deployment, severity="medium", title=f"Incident: {title}",
                         message=f"{description} Re-check the affected area ({category}).")
    else:
        await alert(session, event, deployment.department_id, deployment, severity="low", title=f"Incident: {title}",
                    message=description, action="review")
    await _tell_other_users(session, event, model.id, deployment.department_id,
                            title=f"Incident with {model.name} in another department: {title}",
                            message=f"Category: {category}, severity {severity}. Check whether your use is exposed to the same problem.")
    session.add(audit_entry("incident.reported", user=user, entity_type="incident", entity_id=incident.id,
                            assessment_id=deployment.assessment_id, details={"title": title, "severity": severity, "category": category}))
    return incident


async def resolve_incident(session: AsyncSession, user: User, incident: Incident, *, root_cause: str, resolution: str,
                           lesson: dict | None) -> Incident:
    if user.department_id != incident.department_id:
        raise HTTPException(403, "Only the department that reported the incident can resolve it.")
    if incident.status == "resolved":
        raise HTTPException(409, "This incident is already resolved.")
    incident.status, incident.root_cause, incident.resolution = "resolved", root_cause, resolution
    version = await session.get(ModelVersion, incident.model_version_id)
    deployment = await session.get(Deployment, incident.deployment_id) if incident.deployment_id else None
    lesson_row = None
    if lesson:
        lesson_row = Lesson(model_id=version.model_id, department_id=incident.department_id, incident_id=incident.id,
                            assessment_id=deployment.assessment_id if deployment else None, title=lesson["title"],
                            detail=lesson["detail"], tags=lesson.get("tags", []) + [incident.category])
        session.add(lesson_row)
        await session.flush()
        model = await session.get(AIModel, version.model_id)
        event = await record_event(session, "incident", model_id=model.id, version_id=version.id, deployment=deployment,
                                   source=f"user:{user.id}", payload={"incident_id": incident.id, "resolved": True, "lesson_id": lesson_row.id})
        await _tell_other_users(session, event, model.id, incident.department_id,
                                title=f"New lesson in the registry about {model.name}: {lesson['title']}",
                                message=lesson["detail"])
    session.add(audit_entry("incident.resolved", user=user, entity_type="incident", entity_id=incident.id,
                            assessment_id=deployment.assessment_id if deployment else None,
                            details={"root_cause": root_cause, "lesson_id": lesson_row.id if lesson_row else None,
                                     "deployment_still": deployment.status if deployment else None}))
    return incident


async def complaint_counts(session: AsyncSession, deployment_id: int, now: datetime | None = None) -> dict:
    now = now or _now()
    window_start = now - timedelta(days=SPIKE_WINDOW_DAYS)
    base_start = window_start - timedelta(days=BASELINE_DAYS)

    async def count(start, end):
        return (await session.execute(select(func.count()).select_from(Feedback).where(
            Feedback.deployment_id == deployment_id, Feedback.source.in_(COMPLAINT_SOURCES),
            Feedback.created_at >= start, Feedback.created_at < end))).scalar_one()

    recent, baseline = await count(window_start, now + timedelta(seconds=1)), await count(base_start, window_start)
    recent_rate, base_rate = recent / SPIKE_WINDOW_DAYS, baseline / BASELINE_DAYS
    spike = recent >= SPIKE_MIN_COUNT and recent_rate >= SPIKE_RATIO * max(base_rate, 1 / BASELINE_DAYS)
    return {"recent": recent, "recent_days": SPIKE_WINDOW_DAYS, "baseline": baseline, "baseline_days": BASELINE_DAYS,
            "recent_per_day": round(recent_rate, 3), "baseline_per_day": round(base_rate, 3), "spike": spike}


async def check_complaints(session: AsyncSession, deployment: Deployment) -> dict | None:
    """Fires a complaint_spike trigger once per window and sends the deployment back for reassessment."""
    counts = await complaint_counts(session, deployment.id)
    if not counts["spike"] or deployment.status not in LIVE:
        return None
    already = (await session.execute(select(MonitorEvent.id).where(
        MonitorEvent.trigger_type == "complaint_spike", MonitorEvent.deployment_id == deployment.id,
        MonitorEvent.created_at >= _now() - timedelta(days=SPIKE_WINDOW_DAYS)))).scalars().first()
    if already:
        return None
    model, version = await model_of(session, deployment)
    event = await record_event(session, "complaint_spike", model_id=model.id, version_id=version.id, deployment=deployment,
                               source=MONITOR, payload=counts)
    sent = await _send_back(session, event, deployment, severity="high", title=f"Complaints and appeals are rising: {await _label(session, deployment)}",
                            message=f"{counts['recent']} complaints/appeals in the last {SPIKE_WINDOW_DAYS} days "
                                    f"({counts['recent_per_day']}/day against {counts['baseline_per_day']}/day before).")
    return {"event_id": event.id, "alert_id": sent.id, **counts}


async def add_feedback(session: AsyncSession, deployment: Deployment, *, source: str, language: str, text: str,
                       user: User | None, scripted: bool = False) -> tuple[Feedback, dict | None]:
    row = Feedback(deployment_id=deployment.id, department_id=deployment.department_id, source=source, language=language, text=text)
    session.add(row)
    await session.flush()
    session.add(audit_entry("feedback.recorded", user=user, agent=None if user else "scenario_runner" if scripted else MONITOR,
                            entity_type="feedback", entity_id=row.id, assessment_id=deployment.assessment_id,
                            details={"source": source, "language": language}))
    return row, await check_complaints(session, deployment)


async def report_performance(session: AsyncSession, user: User, deployment: Deployment, *, check_key: str, observed: float,
                             sample_size: int, note: str) -> dict:
    if user.department_id != deployment.department_id:
        raise HTTPException(403, "Performance is reported by the department running the deployment.")
    use_case = await session.get(UseCase, deployment.use_case_id)
    threshold = use_case.thresholds.get(check_key, catalog.DEFAULT_THRESHOLDS[check_key])
    model, version = await model_of(session, deployment)
    payload = {"check_key": check_key, "observed": observed, "threshold": threshold, "sample_size": sample_size, "note": note}
    if observed >= threshold:
        session.add(audit_entry("performance.observed", user=user, entity_type="deployment", entity_id=deployment.id,
                                assessment_id=deployment.assessment_id, details={**payload, "drift": False}))
        return {"drift": False, **payload}
    event = await record_event(session, "performance_drift", model_id=model.id, version_id=version.id, deployment=deployment,
                               source=f"user:{user.id}", payload=payload)
    title = f"{catalog.CHECKS[check_key][1]} has drifted to {observed:.2f} (threshold {threshold:.2f})"
    if threshold - observed > DRIFT_PAUSE_MARGIN:
        await _pause(session, event, deployment, "X3", f"{title}, on {sample_size} samples.")
    else:
        await _send_back(session, event, deployment, severity="medium", title=title, message=f"Measured on {sample_size} samples. {note}")
    return {"drift": True, "event_id": event.id, **payload}


async def check_condition(session: AsyncSession, user: User, deployment: Deployment, index: int, status: str, note: str) -> Deployment:
    """Someone checks that a deployment condition is being followed. A breach sends the deployment back."""
    if user.department_id != deployment.department_id:
        raise HTTPException(403, "Conditions are checked by the department running the deployment.")
    entries = [dict(e) for e in deployment.condition_status] or [
        {"condition": c, "status": "unverified", "checked_at": None, "checked_by": None, "note": ""} for c in deployment.conditions]
    if not 0 <= index < len(entries):
        raise HTTPException(404, f"This deployment has {len(entries)} condition(s); index {index} does not exist.")
    entries[index].update(status=status, checked_at=_now().isoformat(), checked_by=user.full_name, note=note)
    deployment.condition_status = entries
    session.add(audit_entry("condition.checked", user=user, entity_type="deployment", entity_id=deployment.id,
                            assessment_id=deployment.assessment_id, details={"condition": entries[index]["condition"], "status": status, "note": note}))
    if status == "breached":
        model, version = await model_of(session, deployment)
        event = await record_event(session, "condition_breach", model_id=model.id, version_id=version.id, deployment=deployment,
                                   source=f"user:{user.id}", payload={"condition": entries[index]["condition"], "note": note})
        deployment.compliance_status, deployment.compliance_note = "at_risk", f"Condition breached: {entries[index]['condition']}"
        await _send_back(session, event, deployment, severity="high", title=f"Deployment condition breached: {entries[index]['condition'][:120]}",
                         message=note)
    return deployment


# ───────────── quarterly standards check and the periodic scan ─────────────

async def _recheck_compliance(session: AsyncSession, deployment: Deployment) -> dict:
    assessment = await session.get(Assessment, deployment.assessment_id)
    use_case = await session.get(UseCase, deployment.use_case_id)
    evidence = {row.field: row for row in (await session.execute(
        select(ProviderEvidence).where(ProviderEvidence.model_version_id == deployment.model_version_id))).scalars()}
    checks = [c for c in catalog.TRACK_CHECKS[assessment.track or "full"] if catalog.CHECKS[c][0] == "compliance"]
    findings, _ = compliance_rules.run_rules(compliance_rules.Context(card=use_case, risk_tier=assessment.risk_tier, evidence=evidence), checks)
    blockers = [f for f in findings if f["status"] == "non_compliant" and f["severity"] == "blocker"]
    others = [f for f in findings if f["status"] == "non_compliant" and f["severity"] != "blocker"]
    unknown = [f for f in findings if f["status"] == "unknown"]
    conditional = [f for f in findings if f["status"] == "conditional"]
    breached = [e for e in deployment.condition_status if e.get("status") == "breached"]
    if blockers or others:
        status = "non_compliant"
    elif unknown or breached or (conditional and not deployment.conditions):
        status = "at_risk"
    else:
        status = "compliant"
    return {"status": status, "blockers": blockers, "non_compliant": others, "unknown": unknown, "breached_conditions": breached,
            "rules_checked": len(findings)}


async def quarterly_check(session: AsyncSession, user: User) -> dict:
    """Re-run the standards checklist on every live deployment against today's evidence. Non-compliance is never left silent."""
    event = await record_event(session, "quarterly_standards_check", source=f"user:{user.id}", payload={"started_by": user.full_name})
    results = []
    for deployment in list((await session.execute(select(Deployment).where(Deployment.status.in_(LIVE)).order_by(Deployment.id))).scalars()):
        outcome = await _recheck_compliance(session, deployment)
        before = deployment.compliance_status
        # A deployment sent back or paused after a change (new terms, a breach) is not made compliant again by the
        # rules alone: the evidence on file may predate the change. It keeps its status until a person has dealt with it.
        held = outcome["status"] == "compliant" and before != "compliant" and deployment.status != "active"
        after = before if held else outcome["status"]
        deployment.compliance_status = after
        problems = ([f"{f['rule']} {f['title']} not met" for f in outcome["blockers"] + outcome["non_compliant"]]
                    + [f"{f['rule']} {f['title']}: evidence missing" for f in outcome["unknown"]]
                    + [f"condition breached: {e['condition']}" for e in outcome["breached_conditions"]])
        if held:
            deployment.compliance_note = (f"Quarterly check: every applicable rule is met on the evidence on file, but the deployment is "
                                          f"{deployment.status.replace('_', ' ')} after a change, so it stays '{before.replace('_', ' ')}' "
                                          "until the reassessment is decided or the named approver resumes it. "
                                          f"Earlier note: {deployment.compliance_note}")[:1000]
        else:
            deployment.compliance_note = "Quarterly check: " + ("; ".join(problems) if problems else "every applicable rule met.")
        deployment.next_review_due = _now() + timedelta(days=REVIEW_INTERVAL_DAYS)
        label = await _label(session, deployment)
        if outcome["blockers"]:
            await _pause(session, event, deployment, "X2", "; ".join(f"{f['rule']}: {f['note']}" for f in outcome["blockers"]))
        elif outcome["status"] != "compliant":
            await _send_back(session, event, deployment, severity="medium", title=f"Quarterly standards check: {label} is {outcome['status'].replace('_', ' ')}",
                             message=deployment.compliance_note)
        results.append({"deployment_id": deployment.id, "deployment": label, "before": before, "after": after,
                        "status": deployment.status, "note": deployment.compliance_note, "rules_checked": outcome["rules_checked"]})
    event.payload = {**event.payload, "deployments_checked": len(results),
                     "compliant": sum(r["after"] == "compliant" for r in results)}
    return {"event_id": event.id, "results": results}


async def scan(session: AsyncSession) -> dict:
    """The always-on part, run on demand or on a schedule: complaint spikes, overdue reviews, exit rules."""
    found = {"complaint_spikes": [], "overdue_reviews": [], "exit_recommendations": []}
    now = _now()
    for deployment in list((await session.execute(select(Deployment).where(Deployment.status.in_(LIVE)).order_by(Deployment.id))).scalars()):
        spike = await check_complaints(session, deployment)
        if spike:
            found["complaint_spikes"].append({"deployment_id": deployment.id, **spike})
        if deployment.next_review_due and deployment.next_review_due < now:
            found["overdue_reviews"].append({"deployment_id": deployment.id, "due": deployment.next_review_due.isoformat()})
        for item in await exit_rules(session, deployment):
            if item["action"] in ("retire", "replace"):
                found["exit_recommendations"].append({"deployment_id": deployment.id, **item})
    # One alert per problem: a scan that finds the same thing again does not alert again while the first alert is not closed.
    wanted = []
    for item in found["overdue_reviews"]:
        deployment = await session.get(Deployment, item["deployment_id"])
        wanted.append((deployment, "medium", f"Periodic review overdue: {await _label(session, deployment)}",
                       f"The review was due on {item['due'][:10]}. Run the quarterly standards check."))
    for item in found["exit_recommendations"]:
        deployment = await session.get(Deployment, item["deployment_id"])
        wanted.append((deployment, "high", f"Exit rule {item['rule']} ({item['action']}): {await _label(session, deployment)}",
                       item["reason"] + " A named person must decide."))
    new = []
    for deployment, severity, title, message in wanted:
        existing = (await session.execute(select(Alert.id).where(Alert.deployment_id == deployment.id, Alert.title == title,
                                                                 Alert.status != "closed"))).scalars().first()
        if existing is None:
            new.append((deployment, severity, title, message))
    if new:
        event = await record_event(session, "monitor_scan", source=MONITOR,
                                   payload={"overdue": len(found["overdue_reviews"]), "exit": len(found["exit_recommendations"]),
                                            "new_alerts": len(new)})
        for deployment, severity, title, message in new:
            await alert(session, event, deployment.department_id, deployment, severity=severity, title=title, message=message,
                        action="review")
    return found


# ───────────── exit rules ─────────────

async def exit_rules(session: AsyncSession, deployment: Deployment) -> list[dict]:
    """Which exit rules apply right now, each with its action and reason. Advice except where noted above."""
    out = []

    def add(rule: str, detail: str) -> None:
        action, reason = EXIT_RULES[rule]
        out.append({"rule": rule, "action": action, "reason": f"{reason} {detail}".strip()})

    open_high = (await session.execute(select(Incident).where(Incident.deployment_id == deployment.id, Incident.status == "open",
                                                              Incident.severity == "high"))).scalars().all()
    for incident in open_high:
        add("X1", f"Incident #{incident.id}: {incident.title}.")
    if deployment.compliance_status == "non_compliant":
        add("X2", deployment.compliance_note)
    version = await session.get(ModelVersion, deployment.model_version_id)
    pin = (await session.execute(select(ProviderEvidence).where(ProviderEvidence.model_version_id == version.id,
                                                                ProviderEvidence.field == "version_pinning"))).scalar_one_or_none()
    if version.status == "withdrawn" or (version.status == "superseded" and not _pinnable(pin)):
        add("X5", f"Deployed version {version.version} is {version.status}"
                  + (" and cannot be pinned." if version.status == "superseded" else "."))
    if deployment.status == "under_reassessment":
        add("X4", deployment.status_reason)
    rejected = (await session.execute(select(Assessment).where(Assessment.reassessment_of_deployment_id == deployment.id,
                                                               Assessment.status == "rejected"))).scalars().first()
    if rejected:
        add("X6", f"Reassessment {rejected.reference} was rejected.")
    if deployment.status == "paused":
        paused_at = (await session.execute(select(func.max(MonitorEvent.created_at)).where(MonitorEvent.deployment_id == deployment.id))).scalar()
        if paused_at and _now() - paused_at > timedelta(days=PAUSED_TOO_LONG_DAYS):
            add("X7", f"Paused since {paused_at.date()}.")
    return out


# ───────────── human actions on a deployment ─────────────

def _require_approver(user: User, deployment: Deployment, what: str) -> None:
    if not (user.can_approve and user.department_id == deployment.department_id):
        raise HTTPException(403, f"Only the department's named approver can {what} a deployment.")


async def human_action(session: AsyncSession, user: User, deployment: Deployment, action: str, reason: str) -> Deployment:
    _require_approver(user, deployment, action)
    if deployment.status == "retired":
        raise HTTPException(409, "This deployment is retired.")
    if action == "pause":
        await set_status(session, deployment, "paused", f"Paused by {user.full_name}: {reason}", user=user)
    elif action == "retire":
        await set_status(session, deployment, "retired", f"Retired by {user.full_name}: {reason}", user=user)
    elif action == "resume":
        blocking = [r for r in await exit_rules(session, deployment) if r["rule"] in ("X1", "X2", "X6")]
        if blocking:
            raise HTTPException(409, {"message": "Cannot resume while these exit rules apply.", "exit_rules": blocking})
        if deployment.status == "active":
            raise HTTPException(409, "This deployment is already active.")
        await set_status(session, deployment, "active", f"Resumed by {user.full_name}: {reason}", user=user)
    else:
        raise HTTPException(422, f"Unknown action {action}")
    return deployment


async def start_reassessment(session: AsyncSession, user: User, deployment: Deployment, version_label: str | None) -> Assessment:
    """A new assessment of the same use case, linked to the deployment. Evidence from another version is never reused."""
    from app.routers.evidence import resolve_version
    from app.services import planning

    if user.department_id != deployment.department_id:
        raise HTTPException(403, "Only the department running the deployment can reassess it.")
    if deployment.status == "retired":
        raise HTTPException(409, "This deployment is retired.")
    running = (await session.execute(select(Assessment).where(
        Assessment.reassessment_of_deployment_id == deployment.id,
        Assessment.status.notin_(("approved", "approved_with_conditions", "rejected", "blocked"))))).scalars().first()
    if running:
        raise HTTPException(409, f"Reassessment {running.reference} is already in progress (id {running.id}).")
    current_model, _ = await model_of(session, deployment)
    model, version = await resolve_version(session, current_model.slug, version_label)
    use_case = await session.get(UseCase, deployment.use_case_id)
    await set_status(session, deployment, "under_reassessment", f"Reassessment started by {user.full_name} on version {version.version}.", user=user)
    assessment, _ = await planning.start_assessment(session, user, use_case, model, version, None)
    assessment.reassessment_of_deployment_id = deployment.id
    session.add(audit_entry("reassessment.started", user=user, entity_type="deployment", entity_id=deployment.id,
                            assessment_id=assessment.id, details={"version": version.version, "reference": assessment.reference}))
    await session.commit()
    return assessment


async def on_reassessment_decided(session: AsyncSession, assessment: Assessment, approval: Approval,
                                  new_deployment: Deployment | None, user: User) -> None:
    """Called by the human decision on a reassessment: approval replaces the old deployment, rejection pauses it (exit rule X6)."""
    old = await session.get(Deployment, assessment.reassessment_of_deployment_id)
    if old is None or old.status == "retired":
        return
    if new_deployment is not None:
        old.replaced_by_deployment_id = new_deployment.id
        await set_status(session, old, "retired", f"Replaced by deployment {new_deployment.id} after reassessment {assessment.reference}.", user=user)
    else:
        await set_status(session, old, "paused", f"Exit rule X6: reassessment {assessment.reference} was rejected by {user.full_name}.",
                         user=user, rule="X6")
        model, version = await model_of(session, old)
        event = await record_event(session, "exit_rule", model_id=model.id, version_id=version.id,
                                   deployment=old, source=f"user:{user.id}", payload={"rule": "X6", "reassessment": assessment.reference, "rejected": True})
        await alert(session, event, old.department_id, old, severity="high", title=f"Reassessment rejected: {await _label(session, old)}",
                    message=f"{EXIT_RULES['X6'][1]} The deployment is paused. Retire it (POST /deployments/{old.id}/retire) or replace it.",
                    action="pause")
