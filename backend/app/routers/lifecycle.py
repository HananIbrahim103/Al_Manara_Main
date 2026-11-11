"""Phase 5: lifecycle monitor, alerts, deployments, incidents, feedback and metrics."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import AIModel, Alert, Deployment, Feedback, Incident, MonitorEvent, User
from app.routers.evidence import _model
from app.routers.registry import _dept_id
from app.schemas import (
    AlertOut, AssessmentOut, ConditionCheckIn, DeploymentAction, DeploymentOut, FeedbackIn, FeedbackOut, IncidentIn, IncidentOut,
    IncidentResolve, MonitorEventOut, PerformanceIn, ReassessIn, SendBackIn, TriggerIn,
)
from app.security import get_current_user, require_admin
from app.services import lifecycle, metrics

router = APIRouter(tags=["lifecycle"])


async def _deployment(session: AsyncSession, deployment_id: int) -> Deployment:
    deployment = await session.get(Deployment, deployment_id)
    if deployment is None:
        raise HTTPException(404, "No such deployment")
    return deployment


# ───────────── triggers and the monitor ─────────────

@router.post("/lifecycle/events", status_code=201)
async def report_change(body: TriggerIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Report a change. `provider_terms_change` names a model (registry administrator); the others name a deployment
    (its own department). Every department using the model is alerted; affected deployments go back for reassessment."""
    if body.trigger_type == "provider_terms_change":
        if user.role != "admin":
            raise HTTPException(403, "Provider-wide changes are recorded by the registry administrator.")
        if not body.model_slug:
            raise HTTPException(422, "provider_terms_change needs model_slug")
        result = await lifecycle.on_reported_change(session, body.trigger_type, user, description=body.description, details=body.details,
                                                    deployment=None, model=await _model(session, body.model_slug))
    else:
        if body.deployment_id is None:
            raise HTTPException(422, f"{body.trigger_type} needs deployment_id")
        deployment = await _deployment(session, body.deployment_id)
        if user.department_id != deployment.department_id:
            raise HTTPException(403, "Only the department running the deployment can report a change to it.")
        result = await lifecycle.on_reported_change(session, body.trigger_type, user, description=body.description, details=body.details,
                                                    deployment=deployment, model=None)
    await session.commit()
    return result


@router.get("/lifecycle/events", response_model=list[MonitorEventOut])
async def list_events(trigger_type: str | None = None, model: str | None = None, deployment_id: int | None = None, limit: int = 100,
                      _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    query = select(MonitorEvent).order_by(MonitorEvent.id.desc()).limit(min(limit, 500))
    if trigger_type:
        query = query.where(MonitorEvent.trigger_type == trigger_type)
    if model:
        query = query.where(MonitorEvent.model_id == (await _model(session, model)).id)
    if deployment_id:
        query = query.where(MonitorEvent.deployment_id == deployment_id)
    return (await session.execute(query)).scalars().all()


@router.post("/lifecycle/scan")
async def run_scan(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """The always-on monitor, run now: complaint spikes, overdue periodic reviews and exit rules for every live deployment."""
    if user.role not in ("admin", "reviewer"):
        raise HTTPException(403, "Reviewers and the registry administrator can run the monitor.")
    found = await lifecycle.scan(session)
    await session.commit()
    return found


@router.post("/lifecycle/quarterly-check")
async def quarterly_check(user: User = Depends(require_admin), session: AsyncSession = Depends(get_session)):
    """Re-run the standards checklist on every live deployment against today's provider evidence."""
    result = await lifecycle.quarterly_check(session, user)
    await session.commit()
    return result


# ───────────── alerts ─────────────

@router.get("/alerts", response_model=list[AlertOut])
async def list_alerts(department: str | None = None, status: str | None = "open", mine: bool = False,
                      user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Alerts for every department (the registry is shared). `mine=true` limits it to your department."""
    query = select(Alert).order_by(Alert.id.desc())
    if mine and user.department_id:
        query = query.where(Alert.department_id == user.department_id)
    elif department:
        query = query.where(Alert.department_id == await _dept_id(session, department))
    if status:
        query = query.where(Alert.status == status)
    return (await session.execute(query)).scalars().all()


async def _alert_action(session: AsyncSession, alert_id: int, user: User, status: str, note: str) -> Alert:
    alert = await session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "No such alert")
    if user.department_id != alert.department_id:
        raise HTTPException(403, "Only the department the alert was sent to can act on it.")
    if alert.status == "closed":
        raise HTTPException(409, "This alert is closed.")
    from datetime import datetime, timezone

    from app.audit import audit_entry
    alert.status, alert.note = status, note
    alert.acknowledged_by_id, alert.acknowledged_at = user.id, datetime.now(timezone.utc)
    session.add(audit_entry(f"alert.{status}", user=user, entity_type="alert", entity_id=alert.id, details={"note": note}))
    await session.commit()
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
async def acknowledge_alert(alert_id: int, body: SendBackIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _alert_action(session, alert_id, user, "acknowledged", body.reason)


@router.post("/alerts/{alert_id}/close", response_model=AlertOut)
async def close_alert(alert_id: int, body: SendBackIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _alert_action(session, alert_id, user, "closed", body.reason)


# ───────────── deployments ─────────────

@router.get("/deployments/{deployment_id}")
async def deployment_detail(deployment_id: int, _: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """A deployment with its conditions and their status, open alerts, incidents, complaint counts and the exit rules that apply now."""
    deployment = await _deployment(session, deployment_id)
    alerts = (await session.execute(select(Alert).where(Alert.deployment_id == deployment.id).order_by(Alert.id.desc()))).scalars().all()
    incidents = (await session.execute(select(Incident).where(Incident.deployment_id == deployment.id).order_by(Incident.id))).scalars().all()
    return {"deployment": DeploymentOut.model_validate(deployment),
            "exit_rules": await lifecycle.exit_rules(session, deployment),
            "complaints": await lifecycle.complaint_counts(session, deployment.id),
            "alerts": [AlertOut.model_validate(a) for a in alerts],
            "incidents": [IncidentOut.model_validate(i) for i in incidents]}


@router.post("/deployments/{deployment_id}/conditions/{index}", response_model=DeploymentOut)
async def check_condition(deployment_id: int, index: int, body: ConditionCheckIn, user: User = Depends(get_current_user),
                          session: AsyncSession = Depends(get_session)):
    """Record that deployment condition number `index` (from 0) is met or breached. A breach sends the deployment back."""
    deployment = await lifecycle.check_condition(session, user, await _deployment(session, deployment_id), index, body.status, body.note)
    await session.commit()
    return deployment


@router.post("/deployments/{deployment_id}/performance")
async def report_performance(deployment_id: int, body: PerformanceIn, user: User = Depends(get_current_user),
                             session: AsyncSession = Depends(get_session)):
    """Report a measured score from live use (for example a monthly sample audit). Below the threshold is drift."""
    result = await lifecycle.report_performance(session, user, await _deployment(session, deployment_id), check_key=body.check_key,
                                                observed=body.observed_score, sample_size=body.sample_size, note=body.note)
    await session.commit()
    return result


@router.post("/deployments/{deployment_id}/reassess", response_model=AssessmentOut, status_code=201)
async def reassess(deployment_id: int, body: ReassessIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Start the reassessment: a new assessment of the same use case, on the current (or named) version.
    Approving it replaces this deployment; rejecting it pauses this deployment (exit rule X6)."""
    return await lifecycle.start_reassessment(session, user, await _deployment(session, deployment_id), body.version)


async def _human(action: str, deployment_id: int, body: DeploymentAction, user: User, session: AsyncSession) -> Deployment:
    deployment = await lifecycle.human_action(session, user, await _deployment(session, deployment_id), action, body.reason)
    await session.commit()
    return deployment


@router.post("/deployments/{deployment_id}/pause", response_model=DeploymentOut)
async def pause(deployment_id: int, body: DeploymentAction, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _human("pause", deployment_id, body, user, session)


@router.post("/deployments/{deployment_id}/resume", response_model=DeploymentOut)
async def resume(deployment_id: int, body: DeploymentAction, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """The approver resumes a paused or under-reassessment deployment. Refused while an open high-severity incident,
    a blocker non-compliance or a rejected reassessment applies."""
    return await _human("resume", deployment_id, body, user, session)


@router.post("/deployments/{deployment_id}/retire", response_model=DeploymentOut)
async def retire(deployment_id: int, body: DeploymentAction, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return await _human("retire", deployment_id, body, user, session)


# ───────────── incidents and feedback ─────────────

@router.post("/incidents", response_model=IncidentOut, status_code=201)
async def report_incident(body: IncidentIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Report an incident. High severity pauses the deployment (exit rule X1); medium sends it back for reassessment.
    Every other department using the model is told."""
    incident = await lifecycle.report_incident(session, user, await _deployment(session, body.deployment_id), title=body.title,
                                               description=body.description, category=body.category, severity=body.severity)
    await session.commit()
    return incident


@router.post("/incidents/{incident_id}/resolve", response_model=IncidentOut)
async def resolve_incident(incident_id: int, body: IncidentResolve, user: User = Depends(get_current_user),
                           session: AsyncSession = Depends(get_session)):
    """Record the root cause and the fix. A lesson goes to the shared registry and every other user of the model is told.
    A paused deployment stays paused until the approver resumes it."""
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "No such incident")
    await lifecycle.resolve_incident(session, user, incident, root_cause=body.root_cause, resolution=body.resolution,
                                     lesson=body.lesson.model_dump() if body.lesson else None)
    await session.commit()
    return incident


@router.post("/feedback", status_code=201)
async def add_feedback(body: FeedbackIn, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Frontline staff feedback, citizen complaints and appeals, recorded by the department running the service.
    Complaints and appeals are watched for a spike."""
    deployment = await _deployment(session, body.deployment_id)
    if user.department_id != deployment.department_id:
        raise HTTPException(403, "Feedback is recorded by the department running the service.")
    row, spike = await lifecycle.add_feedback(session, deployment, source=body.source, language=body.language, text=body.text, user=user)
    await session.commit()
    return {"feedback": FeedbackOut.model_validate(row), "complaint_spike": spike,
            "complaints": await lifecycle.complaint_counts(session, deployment.id)}


# ───────────── metrics ─────────────

@router.get("/metrics")
async def get_metrics(_: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    """Time saved per assessment against the manual baselines (target 80%) and compliance per approved model (target 100%),
    computed from recorded data only."""
    return await metrics.compute(session)
