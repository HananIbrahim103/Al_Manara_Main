"""The two challenge targets, computed only from recorded data.

Time saved: for each decided assessment, recorded time per step against the seeded manual baseline
for the same steps and tier. The baseline is in working hours, so the headline counts working hours
too: automated seconds, plus review and approval time converted from elapsed clock time to working
hours (x 8/24). The elapsed-clock figure is reported beside it as the conservative reading.
Only steps that were actually recorded are compared, so a skipped step never counts as a saving.

Compliance: share of live approved deployments whose compliance status is 'compliant'.
"""
from statistics import median

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import catalog, llm
from app.models import (
    AgentRun, Alert, Assessment, CheckResult, Department, Deployment, Incident, ManualBaseline, ModelVersion, AIModel,
    StepTiming, UseCase,
)

TARGET_TIME_SAVED, TARGET_COMPLIANCE = 0.80, 1.00
# Elapsed human time -> working hours: 8 working hours in each 24 elapsed (weekends ignored, so still generous to the baseline).
WORKING_HOURS_PER_ELAPSED_HOUR = 8 / 24
DECIDED = ("approved", "approved_with_conditions", "rejected")
HUMAN_STEPS = ("review", "approval")


def _cohort(rows: list[dict]) -> dict:
    if not rows:
        return {"assessments": 0, "note": "No decided assessments in this group yet."}
    manual = sum(r["manual_hours"] for r in rows)
    system = sum(r["system_hours"] for r in rows)
    elapsed = sum(r["elapsed_system_hours"] for r in rows)
    elapsed_saved = round(1 - elapsed / manual, 4) if manual else None
    per_tier = {}
    for tier in catalog.RISK_TIERS:
        own = [r for r in rows if r["risk_tier"] == tier]
        if own:
            m, s = sum(r["manual_hours"] for r in own), sum(r["system_hours"] for r in own)
            per_tier[tier] = {"assessments": len(own), "manual_hours": round(m, 2), "system_hours": round(s, 3),
                              "time_saved": round(1 - s / m, 4) if m else None}
    saved = [r["time_saved"] for r in rows if r["time_saved"] is not None]
    overall = round(1 - system / manual, 4) if manual else None
    return {
        "assessments": len(rows), "manual_hours": round(manual, 2), "system_hours": round(system, 3),
        "automated_hours": round(sum(r["automated_hours"] for r in rows), 4),
        "human_working_hours": round(sum(r["human_working_hours"] for r in rows), 3),
        "time_saved": overall, "median_time_saved": round(median(saved), 4) if saved else None,
        "share_meeting_target": round(sum(s >= TARGET_TIME_SAVED for s in saved) / len(saved), 4) if saved else None,
        "target": TARGET_TIME_SAVED, "target_met": overall is not None and overall >= TARGET_TIME_SAVED,
        "elapsed_clock": {
            "how": "Conservative reading: review and approval counted as elapsed clock time, not working hours.",
            "system_hours": round(elapsed, 3), "time_saved": elapsed_saved,
            "target_met": elapsed_saved is not None and elapsed_saved >= TARGET_TIME_SAVED},
        "by_tier": per_tier,
    }


async def compute(session: AsyncSession) -> dict:
    baselines = {(b.step_key, b.risk_tier): b.manual_hours for b in (await session.execute(select(ManualBaseline))).scalars()}
    assessments = (await session.execute(select(Assessment).where(Assessment.status.in_(DECIDED)).order_by(Assessment.id))).scalars().all()
    timings = {}
    for row in (await session.execute(select(StepTiming))).scalars():
        timings.setdefault(row.assessment_id, []).append(row)
    reuse = {}
    for row in (await session.execute(select(CheckResult.assessment_id, CheckResult.source))).all():
        counts = reuse.setdefault(row.assessment_id, {"reused": 0, "fresh": 0})
        counts["reused" if row.source == "reused" else "fresh"] += 1

    per_assessment = []
    for assessment in assessments:
        steps: dict[str, float] = {}
        for row in timings.get(assessment.id, []):
            steps[row.step_key] = steps.get(row.step_key, 0.0) + row.duration_seconds
        runs = sum(1 for row in timings.get(assessment.id, []) if row.step_key == "testing")
        measured = [s for s in catalog.STEPS if s in steps and (s, assessment.risk_tier) in baselines]
        if not measured:
            continue
        manual = sum(baselines[(s, assessment.risk_tier)] for s in measured)
        automated = sum(steps[s] for s in measured if s not in HUMAN_STEPS) / 3600
        human = sum(steps[s] for s in measured if s in HUMAN_STEPS) / 3600  # elapsed clock hours
        human_working = human * WORKING_HOURS_PER_ELAPSED_HOUR
        system = automated + human_working
        governance = assessment.summary.get("governance", {})
        per_assessment.append({
            "assessment_id": assessment.id, "reference": assessment.reference, "risk_tier": assessment.risk_tier,
            "track": assessment.track, "status": assessment.status, "seeded_history": assessment.is_history,
            "steps_measured": measured, "evaluation_runs": runs, "manual_hours": manual, "automated_hours": round(automated, 5),
            "human_elapsed_hours": round(human, 4), "human_working_hours": round(human_working, 4),
            "system_hours": round(system, 4), "elapsed_system_hours": round(automated + human, 4), "time_saved": round(1 - system / manual, 4) if manual else None,
            "checks_reused": reuse.get(assessment.id, {}).get("reused", 0), "checks_fresh": reuse.get(assessment.id, {}).get("fresh", 0),
            "reviews_parallel": {"elapsed_s": governance.get("review_elapsed_s"), "sum_of_reviews_s": governance.get("sum_of_review_durations_s")}
            if governance.get("review_elapsed_s") is not None else None,
        })

    live = [r for r in per_assessment if not r["seeded_history"]]
    history = [r for r in per_assessment if r["seeded_history"]]

    # ---- compliance per approved model in use ----
    deployments = (await session.execute(select(Deployment).where(Deployment.status != "retired").order_by(Deployment.id))).scalars().all()
    rows = []
    for deployment in deployments:
        use_case = await session.get(UseCase, deployment.use_case_id)
        version = await session.get(ModelVersion, deployment.model_version_id)
        model = await session.get(AIModel, version.model_id)
        department = await session.get(Department, deployment.department_id)
        conditions = deployment.condition_status or []
        rows.append({"deployment_id": deployment.id, "department": department.code, "use_case": use_case.code,
                     "model": f"{model.name} {version.version}", "status": deployment.status,
                     "compliance_status": deployment.compliance_status, "note": deployment.compliance_note,
                     "conditions": {s: sum(c.get("status") == s for c in conditions) for s in ("met", "unverified", "breached")}})
    compliant = sum(r["compliance_status"] == "compliant" for r in rows)
    by_model: dict[str, dict] = {}
    for r in rows:
        entry = by_model.setdefault(r["model"], {"deployments": 0, "compliant": 0})
        entry["deployments"] += 1
        entry["compliant"] += r["compliance_status"] == "compliant"

    runs = (await session.execute(select(AgentRun.cost_usd, AgentRun.llm_model))).all()
    open_alerts = (await session.execute(select(Alert).where(Alert.status == "open"))).scalars().all()
    open_incidents = (await session.execute(select(Incident).where(Incident.status == "open"))).scalars().all()

    return {
        "time_saved": {
            "how": ("Working hours per step against the seeded manual baseline (also working hours) for the same steps and tier. "
                    "Review and approval are recorded as elapsed clock time and converted to working hours (x 8/24); "
                    "'elapsed_clock' shows the conservative figure without that conversion. An assessment evaluated more than once (after a "
                    "failure or a send-back) counts the time of every run and review round: rework is time really spent, and "
                    "the manual baseline is for the whole assessment. In mock mode the automated timings do not reflect real "
                    "model latency."),
            "this_system": _cohort(live),
            "seeded_history": _cohort(history),
            "per_assessment": per_assessment,
        },
        "compliance": {
            "how": "Share of approved deployments still in use (not retired) whose compliance status is 'compliant' at their last check.",
            "deployments": len(rows), "compliant": compliant,
            "rate": round(compliant / len(rows), 4) if rows else None, "target": TARGET_COMPLIANCE,
            "target_met": bool(rows) and compliant == len(rows),
            "by_model": by_model, "per_deployment": rows,
        },
        "operations": {
            "open_alerts": len(open_alerts), "open_alerts_by_action": {a: sum(x.action_required == a for x in open_alerts)
                                                                      for a in ("info", "review", "reassess", "pause")},
            "open_incidents": len(open_incidents),
            "deployments_by_status": {s: sum(d.status == s for d in deployments) for s in ("active", "under_reassessment", "paused")},
            "llm_cost_usd": round(sum(r.cost_usd for r in runs), 6),
            "llm_mode": "mock" if llm.is_mock() else "live",
        },
    }
