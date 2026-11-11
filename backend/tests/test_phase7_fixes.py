"""Regression tests for the bugs found in the 10 November 2026 live audit. Runs after Phases 1-6."""
from app.services import datagen, reuse
from app.services.testing import numbers_in, rule_check

ADMIN = "registry.admin@registry.gov.example"
HR_OFFICER, HR_APPROVER = "daniel.okafor@hrl.gov.example", "noura.alketbi@hrl.gov.example"
HR_SECURITY = "saeed.almarri@hrl.gov.example"


# ───────────── rule checks ─────────────

def test_numbers_are_read_with_spaces_and_joined_hyphens():
    assert 1316.0 in numbers_in("Total: 1 316 accidents")
    assert 1316.0 in numbers_in("Total: 1 316 accidents")
    assert numbers_in("Dubai-1316") == {1316.0}
    assert numbers_in("2024-2025: 80,352.") == {2024.0, 2025.0, 80352.0}
    assert numbers_in("a change of -5 points") == {-5.0}
    assert 2025316.0 not in numbers_in("in 2025 316 accidents")  # a year is not a thousands group


def test_a_short_required_word_must_stand_on_its_own():
    disclosure = {"must_include_any": [["AI", "artificial intelligence", "automated"], ["officer", "human", "person"]]}
    assert rule_check("Please file a complaint by email; an officer will reply.", disclosure)  # 'ai' inside other words
    assert rule_check("I am an AI assistant. An officer makes the decision.", disclosure) == []
    assert rule_check("AI's answers are checked by a human.", disclosure) == []
    assert rule_check("Officers decide.", {"must_include": ["officer"]}) == []  # longer words still match inside plurals


def test_the_absent_row_case_is_also_read_by_the_judge():
    rows = [{"Emirate": e, "Type": t, "Count": 100 * i + j} for i, e in enumerate(["Dubai", "Sharjah", "Ajman"], 1)
            for j, t in enumerate(["Collision", "Run-over", "Rollover"], 1)]
    drafts = datagen.generate({"title": "T", "publisher": "P", "rows": rows, "measure": "Count", "dimensions": ["Emirate", "Type"],
                               "checksum": "abc"}, ["en"])
    absent = next(d for d in drafts if d.kind == "absent")
    assert "rubric" in absent.expected and absent.expected["must_include_any"]


# ───────────── reuse: seeded history is never evidence for a real model ─────────────

def test_seeded_history_is_not_reused_with_a_real_model():
    context = reuse.Context(use_case_id=1, audience_type="internal", data_sensitivity="internal", vulnerable_users=False,
                            risk_tier="low", thresholds={})
    source = reuse.Source(assessment_id=1, reference="ASM-2026-0001", department="HRL", use_case_title="Summariser", status="approved",
                          model_version_id=7, version="2.0", context=context, synthetic=True,
                          checks={"hallucination": reuse.SourceCheck(status="passed", score=0.96, origin_assessment_id=1)})
    target = reuse.Context(use_case_id=2, audience_type="internal", data_sensitivity="internal", vulnerable_users=False,
                           risk_tier="low", thresholds={})
    mock = reuse.evaluate(target, 7, "2.0", ["hallucination"], source)
    assert mock["outcome"] != "blocked" and mock["reused_checks"] == ["hallucination"]
    live = reuse.evaluate(target, 7, "2.0", ["hallucination"], source, allow_synthetic=False)
    assert live["outcome"] == "blocked" and live["reasons"][0]["rule"] == "R11" and live["rerun_checks"] == ["hallucination"]
    source.synthetic = False  # an assessment really run in this system stays reusable
    assert reuse.evaluate(target, 7, "2.0", ["hallucination"], source, allow_synthetic=False)["outcome"] != "blocked"


# ───────────── who may write provider evidence ─────────────

def test_an_officer_cannot_write_provider_evidence(client, login):
    body = dict(status="verified", value={"in_country_option": True, "contractual_commitment": True}, note="Trying to verify it myself.")
    assert client.put("/models/waha-70b/versions/3.3/evidence/data_residency", headers=login(HR_OFFICER), json=body).status_code == 403
    assert client.post("/models/waha-70b/versions", headers=login(HR_OFFICER), json={"version": "9.9"}).status_code == 403
    before = client.get("/models/waha-70b/versions/3.3/evidence/summary", headers=login(HR_OFFICER)).json()["counts"]
    assert client.put("/models/waha-70b/versions/3.3/evidence/pricing", headers=login(HR_SECURITY),
                      json=dict(status="claimed", value={}, note="Read the provider's price page.")).status_code == 200
    assert sum(before.values()) == sum(client.get("/models/waha-70b/versions/3.3/evidence/summary",
                                                  headers=login(HR_OFFICER)).json()["counts"].values())


# ───────────── small endpoint fixes ─────────────

def test_scenario_key_is_not_case_sensitive(client, login):
    refused = client.post("/scenarios/E/run", headers=login(HR_OFFICER))
    assert refused.status_code == 403 and "registry administrator" in refused.json()["detail"]


def test_an_impossible_data_source_id_is_not_found(client, login):
    assert client.get("/data-sources/99999999999999999999", headers=login(HR_OFFICER)).status_code == 404


# ───────────── lifecycle ─────────────

def test_a_second_scan_does_not_repeat_open_alerts(client, login):
    admin = login(ADMIN)
    client.post("/lifecycle/scan", headers=admin)
    first = len(client.get("/alerts?status=open", headers=admin).json())
    assert client.post("/lifecycle/scan", headers=admin).status_code == 200
    assert len(client.get("/alerts?status=open", headers=admin).json()) == first


def test_quarterly_check_does_not_clear_a_provider_terms_change(client, login):
    admin = login(ADMIN)
    client.post("/lifecycle/quarterly-check", headers=admin)
    changed = client.post("/lifecycle/events", headers=admin, json={
        "trigger_type": "provider_terms_change", "model_slug": "sahab-flash",
        "description": "The provider now trains on customer data by default."})
    assert changed.status_code == 201 and changed.json()["alerts"]
    affected = {a["deployment_id"] for a in client.get("/alerts?status=open", headers=admin).json() if a["id"] in changed.json()["alerts"]}
    result = client.post("/lifecycle/quarterly-check", headers=admin).json()["results"]
    held = [r for r in result if r["deployment_id"] in affected]
    assert held and all(r["after"] != "compliant" and r["status"] != "active" for r in held)
    rows = {d["deployment_id"]: d for d in client.get("/metrics", headers=admin).json()["compliance"]["per_deployment"]}
    assert all(rows[i]["compliance_status"] != "compliant" for i in affected)


# ───────────── improvements after the audit ─────────────

def test_evidence_older_than_a_year_is_not_reused():
    from datetime import datetime, timedelta, timezone
    now = datetime(2027, 6, 1, tzinfo=timezone.utc)
    context = reuse.Context(use_case_id=1, audience_type="internal", data_sensitivity="internal", vulnerable_users=False,
                            risk_tier="low", thresholds={})
    source = reuse.Source(assessment_id=1, reference="ASM-2026-0009", department="HRL", use_case_title="Summariser", status="approved",
                          model_version_id=7, version="2.0", context=context, decided_at=now - timedelta(days=200),
                          checks={"hallucination": reuse.SourceCheck(status="passed", score=0.96, origin_assessment_id=1)})
    assert reuse.evaluate(context, 7, "2.0", ["hallucination"], source, now=now)["outcome"] != "blocked"
    source.decided_at = now - timedelta(days=reuse.REUSE_MAX_AGE_DAYS + 1)
    old = reuse.evaluate(context, 7, "2.0", ["hallucination"], source, now=now)
    assert old["outcome"] == "blocked" and old["reasons"][0]["rule"] == "R12"


def test_a_rate_limited_call_waits_and_tries_again(monkeypatch):
    import asyncio

    import httpx

    from app import llm
    calls, waits = [], []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            return httpx.Response(429, headers={"retry-after": "7"} if len(calls) == 1 else {}, json={"error": "slow down"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {"prompt_tokens": 3, "completion_tokens": 1, "cost": 0.001}})

    async def no_sleep(seconds):
        waits.append(seconds)

    async def run():
        client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        monkeypatch.setattr(llm, "_shared_client", lambda: client)
        monkeypatch.setattr(llm.asyncio, "sleep", no_sleep)
        try:
            return await llm.chat("some/model", [{"role": "user", "content": "hi"}])
        finally:
            await client.aclose()

    reply = asyncio.run(run())
    assert reply["content"] == "ok" and len(calls) == 3
    assert 7 <= waits[0] < 7.5 and 2 <= waits[1] < 2.5  # the provider's Retry-After first, then the doubling wait


def test_a_document_of_equal_weight_does_not_replace_evidence_on_file(client, login):
    headers = login(HR_SECURITY)
    first = dict(title="Provider FAQ", kind="documentation", text="Version pinning is available for 12 months.")
    second = dict(title="Sales email", kind="email", text="Pinning of a snapshot is possible for 3 months only.")
    url = "/models/najm-mini/versions"
    version = client.get("/models/najm-mini", headers=headers).json()["versions"][-1]["version"]
    client.put(f"{url}/{version}/evidence/version_pinning", headers=headers, json=dict(status="missing", value={}, note="Reset for this test."))
    one = client.post(f"{url}/{version}/evidence", headers=headers, json={"documents": [first]}).json()
    assert {"version_pinning"} <= {c["field"] for c in one["changes"]}
    two = client.post(f"{url}/{version}/evidence", headers=headers, json={"documents": [second]}).json()
    assert "version_pinning" not in {c["field"] for c in two["changes"]}
    kept = {k["field"]: k for k in two["kept_existing"]}
    assert kept["version_pinning"]["on_file_from"] == "Provider FAQ" and kept["version_pinning"]["not_applied_from"] == "Sales email"


def test_reuse_from_seeded_history_is_labelled_and_reruns_are_counted(client, login):
    officer = login(HR_OFFICER)
    started = client.post("/assessments", headers=officer, json={"use_case_code": "HRL-POLICY-QA", "model_slug": "najm-mini"}).json()
    assert client.post(f"/assessments/{started['id']}/evaluate?wait=true", headers=officer).status_code == 202
    client.post(f"/assessments/{started['id']}/submit-for-review", headers=officer)
    record = client.get(f"/assessments/{started['id']}/decision-record", headers=officer).json()["content"]
    reused = [c for c in record["evidence_used"]["checks"] if c["source"] == "reused"]
    labelled = any("seeded example history" in line for line in record["limitations"])
    seeded_ids = {a["id"] for a in client.get("/registry/assessments", headers=officer).json() if a.get("is_history")}
    assert labelled == any(c["reused_from_assessment_id"] in seeded_ids for c in reused)
    metrics = client.get("/metrics", headers=officer).json()["time_saved"]
    assert all(row["evaluation_runs"] >= 0 for row in metrics["per_assessment"]) and "every run" in metrics["how"]
