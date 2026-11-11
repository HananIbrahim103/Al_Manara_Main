"""Phase 1 checks. Run against a migrated and seeded database:

    alembic upgrade head && python -m app.seed && pytest
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app import catalog
from app.db import make_sync_session
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def auth(client):
    response = client.post("/auth/login", json={"email": "noura.alketbi@hrl.gov.example"})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_health(client):
    assert client.get("/health").json()["status"] == "ok"


def test_registry_requires_login(client):
    assert client.get("/departments").status_code == 401
    assert client.get("/registry/assessments").status_code == 401
    assert client.get("/audit", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_login_and_me(client, auth):
    me = client.get("/auth/me", headers=auth).json()
    assert me["full_name"] == "Noura Al Ketbi" and me["can_approve"] is True
    assert client.post("/auth/login", json={"email": "nobody@example.com"}).status_code == 404


def test_four_departments_two_internal_two_citizen_facing(client, auth):
    departments = client.get("/departments", headers=auth).json()
    assert [d["code"] for d in departments] == ["RID", "HRL", "TRF", "SCS"]
    assert [d["audience_type"] for d in departments] == ["internal", "internal", "citizen_facing", "citizen_facing"]


def test_each_department_has_four_reviewers_and_one_named_approver(client, auth):
    for code in ("RID", "HRL", "TRF", "SCS"):
        detail = client.get(f"/departments/{code}", headers=auth).json()
        reviewers = [u for u in detail["users"] if u["role"] == "reviewer"]
        assert len(reviewers) == 4
        assert sum(u["can_approve"] for u in detail["users"]) == 1
        assert len(detail["use_cases"]) >= 3


def test_every_model_version_has_full_normalised_evidence_and_gaps_are_flagged(client, auth):
    models = client.get("/models", headers=auth).json()
    assert len(models) == 4
    for model in models:
        detail = client.get(f"/models/{model['slug']}", headers=auth).json()
        for version in detail["versions"]:
            assert {e["field"] for e in version["evidence"]} == set(catalog.EVIDENCE_FIELDS)
    waha = client.get("/models/waha-70b", headers=auth).json()["versions"][0]
    assert {"fairness_evaluation", "benchmark_arabic", "update_policy"} <= set(waha["evidence_gaps"])


def test_history_has_conditions_a_rejection_and_incidents(client, auth):
    assessments = client.get("/registry/assessments", headers=auth).json()
    statuses = [a["status"] for a in assessments]
    assert statuses.count("approved_with_conditions") == 3 and "rejected" in statuses and "approved" in statuses
    rejected = client.get("/registry/assessments?status=rejected", headers=auth).json()[0]
    detail = client.get(f"/registry/assessments/{rejected['id']}", headers=auth).json()
    assert detail["approval"]["decision"] == "rejected" and detail["approval"]["reason"]
    assert any(c["check_key"] == "fairness" and c["status"] == "failed" for c in detail["check_results"])
    assert len(client.get("/registry/incidents", headers=auth).json()) == 2
    assert len(client.get("/registry/lessons?tag=fairness", headers=auth).json()) == 1


def test_every_past_decision_was_made_by_the_departments_named_approver(client, auth):
    users = {u["id"]: u for u in client.get("/users", headers=auth).json()}
    for assessment in client.get("/registry/assessments", headers=auth).json():
        detail = client.get(f"/registry/assessments/{assessment['id']}", headers=auth).json()
        approver = users[detail["approval"]["approver_id"]]
        assert approver["can_approve"] and approver["department_id"] == detail["department_id"]


def test_same_model_is_deployed_in_more_than_one_department(client, auth):
    deployments = client.get("/registry/deployments?model=sahab-flash", headers=auth).json()
    assert len({d["department_id"] for d in deployments}) == 2


def test_every_use_case_has_a_test_set_with_arabic_and_english(client, auth):
    use_cases = client.get("/use-cases", headers=auth).json()
    assert len(use_cases) == 14
    for use_case in use_cases:
        sets = client.get(f"/test-sets?use_case={use_case['code']}", headers=auth).json()
        own = [s for s in sets if s["code"] == use_case["code"]]  # plus DATA-<code> when it relies on open data
        assert len(own) == 1 and all(s["code"] in (use_case["code"], "DATA-" + use_case["code"]) for s in sets)
        cases = client.get(f"/test-sets/{own[0]['code']}", headers=auth).json()["cases"]
        languages = {c["language"] for c in cases}
        assert "en" in languages and languages & {"ar-msa", "ar-gulf"}
    shared = client.get("/test-sets?shared_only=true", headers=auth).json()
    assert len(shared) == 7


def test_baselines_cover_every_step_and_tier(client, auth):
    baselines = client.get("/baselines", headers=auth).json()
    assert len(baselines) == len(catalog.STEPS) * len(catalog.RISK_TIERS)


def test_audit_log_is_append_only(client, auth):
    assert any(row["action"] == "auth.login" for row in client.get("/audit", headers=auth).json())
    for statement in ("UPDATE audit_log SET action = 'tampered'", "DELETE FROM audit_log", "TRUNCATE audit_log"):
        session = make_sync_session()
        try:
            with pytest.raises(DBAPIError, match="append-only"):
                session.execute(text(statement))
        finally:
            session.rollback()
            session.close()


def test_a_freshly_seeded_test_bank_needs_no_sync(seeded_database):
    from app.db import make_sync_session
    from app.seed.__main__ import sync_test_bank

    session = make_sync_session()
    try:
        assert sync_test_bank(session) == {"added": 0, "retired": 0}
    finally:
        session.rollback()
        session.close()


def test_the_local_frontend_is_always_allowed(monkeypatch):
    from app.config import Settings

    settings = Settings(cors_origins="https://almanara.vercel.app")
    assert settings.cors_origin_list[0] == "https://almanara.vercel.app"
    assert {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"} <= set(settings.cors_origin_list)
