"""Load the synthetic seed data.

    python -m app.seed            load once; does nothing if data is already there
    python -m app.seed --reset    drop every table, re-run migrations, load again
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from app import catalog
from app.audit import audit_entry
from app.db import make_sync_session
from app.models import (
    AIModel, Approval, Assessment, CheckResult, Concern, DataSource, DecisionRecord, Department, Deployment,
    Feedback, Incident, Lesson, ManualBaseline, ModelVersion, ProviderEvidence, Review, StepTiming,
    TestCase, TestSet, UseCase, UseCaseDataSource, User,
)
from app.seed import opendata, org, registry, testsets

BACKEND_DIR = Path(__file__).resolve().parents[2]


def reset_schema() -> None:
    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def seed(session) -> dict:
    # ---- departments and users ----
    depts = {d["code"]: Department(**d) for d in org.DEPARTMENTS}
    session.add_all(depts.values())
    session.flush()

    users: dict[str, User] = {}
    for dept_code, name, local, title, role, reviewer_role, can_approve in org.USERS:
        users[local] = User(
            department_id=depts[dept_code].id if dept_code else None, full_name=name,
            email=f"{local}@{org.EMAIL_DOMAIN[dept_code]}", title=title, role=role,
            reviewer_role=reviewer_role, can_approve=can_approve,
        )
    session.add_all(users.values())
    session.flush()

    def reviewer(dept_code: str, reviewer_role: str) -> User:
        return next(u for u in users.values() if u.department_id == depts[dept_code].id and u.reviewer_role == reviewer_role)

    # ---- use-case cards ----
    use_cases: dict[str, UseCase] = {}
    dept_of_use_case: dict[str, str] = {}
    for code, dept_code, creator, card in org.USE_CASES:
        use_cases[code] = UseCase(code=code, department_id=depts[dept_code].id, created_by_id=users[creator].id, **card)
        dept_of_use_case[code] = dept_code
    session.add_all(use_cases.values())

    # ---- models, versions, normalised provider evidence ----
    models: dict[str, AIModel] = {}
    versions: dict[tuple, ModelVersion] = {}
    for spec in registry.MODELS:
        spec = dict(spec)
        version_specs = spec.pop("versions")
        model = AIModel(**spec)
        session.add(model)
        session.flush()
        models[model.slug] = model
        for version, status, released, changelog in version_specs:
            versions[(model.slug, version)] = ModelVersion(
                model_id=model.id, version=version, status=status, released_at=released, changelog=changelog)
    session.add_all(versions.values())
    session.flush()

    for key, fields in registry.EVIDENCE.items():
        assert set(fields) == set(catalog.EVIDENCE_FIELDS), f"evidence for {key} must cover every field"
        for field, (status, value, source, note) in fields.items():
            session.add(ProviderEvidence(model_version_id=versions[key].id, field=field, status=status,
                                         value=value, source=source, note=note))

    # ---- test sets ----
    case_count = 0
    for spec in testsets.TEST_SETS:
        test_set = TestSet(
            code=spec["code"], title=spec["title"], system_prompt=spec["system_prompt"],
            description=spec.get("description", ""),
            use_case_id=use_cases[spec["use_case"]].id if spec["use_case"] else None,
        )
        session.add(test_set)
        session.flush()
        for test_case in spec["cases"]:
            assert test_case["check_key"] in catalog.CHECKS, test_case["check_key"]
            session.add(TestCase(test_set_id=test_set.id, **test_case))
            case_count += 1

    # ---- compliance and procurement checklist (defined in code, mirrored here so it can be listed) ----
    from app.models import ComplianceRule
    from app.services.compliance import RULES
    for rule in RULES:
        session.add(ComplianceRule(code=rule.code, check_key=rule.check_key, title=rule.title, requirement=rule.requirement,
                                   source_ref=rule.source_ref, severity=rule.severity))

    # ---- manual baselines ----
    for step, (hours, description) in registry.BASELINES.items():
        for tier, value in zip(catalog.RISK_TIERS, hours):
            session.add(ManualBaseline(step_key=step, risk_tier=tier, manual_hours=value, description=description))

    session.flush()

    # ---- past assessments, with reviews, concerns, decision record, approval, deployment ----
    assessments: dict[str, Assessment] = {}
    deployments: dict[str, Deployment] = {}
    for item in registry.HISTORY:
        use_case = use_cases[item["use_case"]]
        dept_code = dept_of_use_case[item["use_case"]]
        dept = depts[dept_code]
        version = versions[item["model"]]
        model = models[item["model"][0]]
        approver = users[item["approver"]]
        assert approver.can_approve and approver.department_id == dept.id, "approver must be the department's named approver"

        passed, failed, warnings = [], [], []
        results = []
        for check_key, score in item["scores"].items():
            threshold = use_case.thresholds[check_key]
            ok = score >= threshold
            (passed if ok else failed).append(check_key)
            results.append(dict(check_key=check_key, score=score, threshold=threshold,
                                status="passed" if ok else "failed", details={}))
        for check_key, (status, note) in item["rules"].items():
            {"passed": passed, "failed": failed, "warning": warnings}[status].append(check_key)
            results.append(dict(check_key=check_key, score=None, threshold=None, status=status, details={"note": note}))

        recommendation = {"approved": "approve", "approved_with_conditions": "approve_with_conditions", "rejected": "reject"}[item["status"]]
        assessment = Assessment(
            reference=item["reference"], use_case_id=use_case.id, model_version_id=version.id, department_id=dept.id,
            requested_by_id=users[item["requested_by"]].id, status=item["status"], risk_tier=item["risk_tier"],
            track=item["track"],
            tier_rationale=[{"rule": "seeded", "floor": None, "reason": reason, "decisive": False} for reason in item["tier_rationale"]], recommendation=recommendation,
            summary=dict(checks_passed=len(passed), checks_failed=len(failed), checks_warning=len(warnings),
                         failed_checks=failed, warning_checks=warnings),
            is_history=True, started_at=item["started"], completed_at=item["decided"],
        )
        session.add(assessment)
        session.flush()
        assessments[item["reference"]] = assessment

        for result in results:
            session.add(CheckResult(assessment_id=assessment.id, agent=catalog.CHECKS[result["check_key"]][0],
                                    source="fresh", created_at=item["started"] + timedelta(hours=2), **result))

        review_sent = item["started"] + timedelta(hours=3)
        concern_roles = {c[0] for c in item["concerns"]}
        rejected = item["status"] == "rejected"
        for role in item["reviewers"]:
            person = reviewer(dept_code, role)
            if role in concern_roles:
                status = "objection" if rejected else "concerns"
                comment = "Concern raised; see the concerns list."
            else:
                status, comment = "no_objection", "Reviewed the evidence for my area. No objection."
            session.add(Review(assessment_id=assessment.id, reviewer_id=person.id, reviewer_role=role, status=status,
                               comment=comment, assigned_at=review_sent,
                               submitted_at=review_sent + timedelta(seconds=item["timings"]["review"] * 0.6)))
        for role, title, detail, severity, resolution in item["concerns"]:
            person = reviewer(dept_code, role)
            resolved = bool(resolution)
            session.add(Concern(
                assessment_id=assessment.id, raised_by_id=person.id, title=title, detail=detail, severity=severity,
                status="resolved" if resolved else "open", resolution=resolution,
                resolved_by_id=approver.id if resolved else None, created_at=review_sent + timedelta(days=1),
                resolved_at=item["decided"] - timedelta(days=1) if resolved else None))

        owner = dict(name=approver.full_name, title=approver.title, department=dept.name)
        session.add(DecisionRecord(
            assessment_id=assessment.id, version=1, created_at=item["decided"] - timedelta(hours=4),
            plain_summary=f"{model.name} {version.version} for '{use_case.title}': risk tier {item['risk_tier']}. "
                          f"System recommendation: {recommendation.replace('_', ' ')}. {item['reason']}",
            content=dict(
                use_case=use_case.title, model=f"{model.name} {version.version}", risk_tier=item["risk_tier"],
                recommendation=recommendation, assumptions=item["assumptions"], limitations=item["limitations"],
                evidence_used=[f"{catalog.CHECKS[r['check_key']][1]}: {r['status']}"
                               + (f" ({r['score']:.2f} against {r['threshold']:.2f})" if r["score"] is not None else "")
                               for r in results],
                conditions=item["conditions"], residual_risk=item["residual_risk"], accountable_owner=owner)))
        session.add(Approval(
            assessment_id=assessment.id, decision=item["status"], approver_id=approver.id,
            risk_accepted_by_id=None if rejected else approver.id, reason=item["reason"],
            conditions=item["conditions"], decided_at=item["decided"]))

        for step, seconds in item["timings"].items():
            mode = "human" if step in ("review", "approval") else "automated"
            session.add(StepTiming(assessment_id=assessment.id, step_key=step, mode=mode,
                                   duration_seconds=seconds, started_at=item["started"]))

        if not rejected:
            deployment = Deployment(
                assessment_id=assessment.id, department_id=dept.id, use_case_id=use_case.id,
                model_version_id=version.id, status="active", conditions=item["conditions"],
                compliance_status="compliant", deployed_at=item["decided"] + timedelta(days=5),
                next_review_due=item["decided"] + timedelta(days=95))
            session.add(deployment)
            session.flush()
            deployments[item["reference"]] = deployment

        session.add(audit_entry("seed.history_assessment", entity_type="assessment", entity_id=assessment.id,
                                assessment_id=assessment.id,
                                details=dict(reference=item["reference"], decision=item["status"], approver=approver.full_name)))

    # ---- incidents, lessons, feedback ----
    incidents: dict[str, Incident] = {}
    for item in registry.INCIDENTS:
        source = assessments[item["assessment"]]
        incident = Incident(
            deployment_id=deployments[item["assessment"]].id, department_id=source.department_id,
            model_version_id=source.model_version_id, title=item["title"], description=item["description"],
            category=item["category"], severity=item["severity"], status=item["status"],
            root_cause=item["root_cause"], resolution=item["resolution"],
            reported_by_id=users[item["reported_by"]].id, occurred_at=item["occurred"])
        session.add(incident)
        session.flush()
        incidents[item["key"]] = incident

    for item in registry.LESSONS:
        incident = incidents.get(item["incident"])
        session.add(Lesson(
            model_id=models[item["model"]].id, department_id=depts[item["dept"]].id,
            incident_id=incident.id if incident else None, assessment_id=assessments[item["assessment"]].id,
            title=item["title"], detail=item["detail"], tags=item["tags"],
            created_at=(incident.occurred_at if incident else assessments[item["assessment"]].completed_at) + timedelta(days=7)))

    for reference, source, language, text, when in registry.FEEDBACK:
        deployment = deployments[reference]
        session.add(Feedback(deployment_id=deployment.id, department_id=deployment.department_id,
                             source=source, language=language, text=text, created_at=when))

    open_cases = seed_open_data(session, use_cases)

    counts = dict(departments=len(depts), users=len(users), use_cases=len(use_cases), models=len(models),
                  model_versions=len(versions), test_sets=len(testsets.TEST_SETS), test_cases=case_count,
                  past_assessments=len(assessments), deployments=len(deployments), incidents=len(incidents),
                  lessons=len(registry.LESSONS), feedback=len(registry.FEEDBACK),
                  open_data_sources=len(opendata.SOURCES), open_data_cases=open_cases)
    session.add(audit_entry("seed.loaded", details=counts))
    return counts


def seed_open_data(session, use_cases: dict[str, UseCase]) -> int:
    """Real open data (Bayanat snapshot) linked to the Use-Case Cards, with test cases computed from it."""
    from app.services import opendata as opendata_service

    snapshot = opendata.load()
    open_cases = 0
    data_sets: dict[str, TestSet] = {}
    for key, _token, linked, _why in opendata.SOURCES:
        ds = DataSource(key=key, portal="bayanat", **snapshot[key])
        session.add(ds)
        session.flush()
        for code in linked:
            use_case = use_cases[code]
            session.add(UseCaseDataSource(use_case_id=use_case.id, data_source_id=ds.id))
            if code not in data_sets:
                own = session.execute(select(TestSet).where(TestSet.code == code)).scalar_one_or_none()
                data_sets[code] = opendata_service.data_set_for(use_case, own.system_prompt if own else "")
                session.add(data_sets[code])
                session.flush()
            rows = opendata_service.case_rows(data_sets[code].id, ds, use_case.languages)
            session.add_all(rows)
            open_cases += len(rows)
    return open_cases


def sync_test_bank(session) -> dict:
    """Bring an already-seeded database's test bank in line with testsets.py.

    A case whose wording or expectations changed is marked superseded (its past test runs keep pointing at it) and
    the new version is added. Nothing is deleted.
    """
    def key(item) -> str:
        return json.dumps([item["check_key"], item["language"], item["prompt"], item["expected"]], sort_keys=True, ensure_ascii=False)

    added = retired = 0
    for spec in testsets.TEST_SETS:
        test_set = session.execute(select(TestSet).where(TestSet.code == spec["code"])).scalar_one_or_none()
        if test_set is None:
            continue
        wanted = {key(c): c for c in spec["cases"]}
        current = session.execute(select(TestCase).where(TestCase.test_set_id == test_set.id, TestCase.origin == "seeded")).scalars().all()
        live = {}
        for row in current:
            if (row.meta or {}).get("superseded"):
                continue
            k = key(dict(check_key=row.check_key, language=row.language, prompt=row.prompt, expected=row.expected))
            if k in wanted:
                live[k] = row
            else:
                row.meta = {**(row.meta or {}), "superseded": True}
                retired += 1
        for k, item in wanted.items():
            if k not in live:
                session.add(TestCase(test_set_id=test_set.id, **item))
                added += 1
        if test_set.system_prompt != spec["system_prompt"]:
            test_set.system_prompt = spec["system_prompt"]

    # Open-data cases are written by code from each table. When that code changes (a new rubric, a new kind of
    # question), the cases of an existing database are brought in line the same way.
    from app.services import opendata as opendata_service
    for link in session.execute(select(UseCaseDataSource)).scalars().all():
        use_case, ds = session.get(UseCase, link.use_case_id), session.get(DataSource, link.data_source_id)
        test_set = session.execute(select(TestSet).where(TestSet.code == f"{opendata_service.SET_PREFIX}{use_case.code}")).scalar_one_or_none()
        if test_set is None:
            continue
        fresh = {key(dict(check_key=r.check_key, language=r.language, prompt=r.prompt, expected=r.expected)): r
                 for r in opendata_service.case_rows(test_set.id, ds, use_case.languages)}
        kept = set()
        for row in session.execute(select(TestCase).where(TestCase.test_set_id == test_set.id, TestCase.origin == "bayanat")).scalars().all():
            if (row.meta or {}).get("superseded") or (row.meta or {}).get("data_source_id") != ds.id:
                continue
            k = key(dict(check_key=row.check_key, language=row.language, prompt=row.prompt, expected=row.expected))
            if k in fresh:
                kept.add(k)
            else:
                row.meta = {**row.meta, "superseded": True}
                retired += 1
        for k, row in fresh.items():
            if k not in kept:
                session.add(row)
                added += 1
    if added or retired:
        session.add(audit_entry("seed.test_bank_synced", details={"added": added, "retired": retired}))
    return {"added": added, "retired": retired}


def main() -> None:
    if "--reset" in sys.argv:
        reset_schema()
    session = make_sync_session()
    try:
        if session.execute(select(func.count()).select_from(Department)).scalar_one() > 0:
            synced = sync_test_bank(session)
            session.commit()
            if synced["added"] or synced["retired"]:
                print(f"Test bank synced: {synced['added']} case(s) added, {synced['retired']} superseded.")
            # An older database (seeded before open data existed) gets the open data on its own.
            if session.execute(select(func.count()).select_from(DataSource)).scalar_one() == 0:
                use_cases = {u.code: u for u in session.execute(select(UseCase)).scalars()}
                added = seed_open_data(session, use_cases)
                session.add(audit_entry("seed.open_data_added", details={"sources": len(opendata.SOURCES), "test_cases": added}))
                session.commit()
                print(f"Added open data: {len(opendata.SOURCES)} Bayanat tables, {added} test cases.")
                return
            print("Seed data already present; nothing to do. Use --reset to reload.")
            return
        counts = seed(session)
        session.commit()
        print("Seeded:", ", ".join(f"{value} {name}" for name, value in counts.items()))
    finally:
        session.close()


if __name__ == "__main__":
    main()
