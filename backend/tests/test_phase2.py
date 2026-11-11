"""Phase 2: intake and risk tiering, evidence normalisation, reuse rules and the assessment plan."""
from types import SimpleNamespace

import pytest

from app import catalog
from app.services import evidence as evidence_service
from app.services.tiering import assess_tier

HR_OFFICER = "daniel.okafor@hrl.gov.example"
RID_OFFICER = "ahmed.alnuaimi@rid.gov.example"
SCS_OFFICER = "reem.altunaiji@scs.gov.example"
SCS_CIVIL = "joseph.mathew@scs.gov.example"


def card(**overrides):
    base = dict(audience_type="internal", data_sensitivity="internal", consequence_of_error="minor",
                autonomy_level="assistive", human_oversight="sampled", vulnerable_users=False, languages=["en"])
    return SimpleNamespace(**{**base, **overrides})


# ───────────── risk tiering ─────────────

@pytest.mark.parametrize("overrides, tier, decisive_rule", [
    ({}, "low", "T0"),
    ({"data_sensitivity": "personal"}, "medium", "T1"),
    ({"data_sensitivity": "sensitive_personal"}, "high", "T2"),
    ({"consequence_of_error": "serious"}, "high", "T4"),
    ({"audience_type": "citizen_facing"}, "medium", "T5"),
    ({"audience_type": "citizen_facing", "vulnerable_users": True}, "high", "T6"),
    ({"autonomy_level": "autonomous"}, "critical", "T8"),
    ({"consequence_of_error": "severe", "vulnerable_users": True}, "critical", "T10"),
    ({"human_oversight": "none"}, "medium", "T12"),
])
def test_tier_rules(overrides, tier, decisive_rule):
    result = assess_tier(card(**overrides))
    assert result.risk_tier == tier
    assert decisive_rule in [r["rule"] for r in result.rationale if r["decisive"]]
    assert result.track == catalog.TRACK_FOR_TIER[tier]


def test_seeded_use_cases_get_the_expected_tiers(client, auth):
    expected = {"HRL-POLICY-QA": "low", "HRL-SUMM": "low", "HRL-PERMIT": "medium", "HRL-CV": "high",
                "RID-SUMM": "high", "RID-EXTRACT": "high", "TRF-ASSIST": "high", "TRF-TRIAGE": "medium",
                "SCS-ASSIST": "high", "SCS-ELIG": "critical", "SCS-ACCESS": "high"}
    for code, tier in expected.items():
        body = client.get(f"/use-cases/{code}/tier", headers=auth).json()
        assert body["risk_tier"] == tier, code
        assert body["rationale"] and all(r["reason"] for r in body["rationale"])


def test_computed_tier_matches_every_past_assessment(client, auth):
    for assessment in client.get("/registry/assessments", headers=auth).json():
        if not assessment["is_history"]:
            continue
        detail = client.get(f"/registry/assessments/{assessment['id']}", headers=auth).json()
        tier = client.get(f"/use-cases/{detail['use_case']['code']}/tier", headers=auth).json()
        assert tier["risk_tier"] == assessment["risk_tier"]


def test_fast_track_runs_fewer_checks_than_full(client, auth):
    low = client.get("/use-cases/HRL-POLICY-QA/tier", headers=auth).json()
    high = client.get("/use-cases/TRF-ASSIST/tier", headers=auth).json()
    assert low["track"] == "fast" and high["track"] == "full"
    assert len(low["required_checks"]) < len(high["required_checks"])
    assert "fairness" not in low["required_checks"] and "fairness" in high["required_checks"]


def test_create_use_case_card(client, login):
    headers = login(HR_OFFICER)
    body = dict(title="Payslip question assistant", purpose="Answer employees' questions about their own payslip.",
                audience_type="internal", affected_users=["employees"], data_sensitivity="personal",
                consequence_of_error="moderate", autonomy_level="assistive", human_oversight="sampled",
                languages=["en", "ar-msa"], thresholds={"task_accuracy": 0.93})
    created = client.post("/use-cases", headers=headers, json=body)
    assert created.status_code == 201, created.text
    use_case = created.json()
    assert use_case["code"].startswith("HRL-UC-")
    assert use_case["thresholds"]["task_accuracy"] == 0.93 and use_case["thresholds"]["hallucination"] == 0.90
    assert client.get(f"/use-cases/{use_case['code']}/tier", headers=headers).json()["risk_tier"] == "medium"
    assert client.post("/tier/preview", headers=headers, json={**body, "autonomy_level": "autonomous"}).json()["risk_tier"] == "critical"
    assert client.post("/use-cases", headers=headers, json={**body, "data_sensitivity": "secret"}).status_code == 422
    assert client.post("/use-cases", headers=headers, json={**body, "thresholds": {"vibes": 0.5}}).status_code == 422


# ───────────── evidence normalisation ─────────────

def test_status_comes_from_the_kind_of_document_not_from_the_model():
    assert evidence_service.classify("data_residency", "contract", {})[0] == "verified"
    assert evidence_service.classify("data_residency", "press_release", {})[0] == "claimed"
    assert evidence_service.classify("benchmark_arabic", "marketing", {})[0] == "unsupported"
    assert evidence_service.classify("benchmark_general", "evaluation_report", {"method_disclosed": False})[0] == "claimed"
    assert evidence_service.classify("benchmark_general", "documentation", {"method_disclosed": False})[0] == "unsupported"
    assert evidence_service.classify("intended_use", "model_card", {})[0] == "verified"


def test_benchmark_scales_are_put_on_one_scale():
    assert evidence_service.normalise("benchmark_arabic", {"score": 0.71, "scale": "0-1"})["score_0_100"] == 71.0
    assert evidence_service.normalise("benchmark_general", {"score": 82, "scale": "0-100"})["score_0_100"] == 82.0
    assert evidence_service.normalise("benchmark_general", {"score": 1450, "scale": "elo"})["score_0_100"] is None


def test_register_model_then_submit_documents(client, login):
    headers = login(HR_OFFICER)
    created = client.post("/models", headers=headers, json=dict(
        slug="qamar-nano", name="Qamar Nano", provider="Provider E", openrouter_id="example/qamar-nano", version="1.0"))
    # Provider evidence decides compliance results: an officer cannot write it, a named reviewer can.
    assert client.post("/models/qamar-nano/versions/1.0/evidence", headers=headers, json={"documents": [
        dict(title="x", kind="contract", text="Data is processed in the UAE.")]}).status_code == 403
    headers = login("saeed.almarri@hrl.gov.example")
    assert created.status_code == 201, created.text
    summary = client.get("/models/qamar-nano/versions/1.0/evidence/summary", headers=headers).json()
    assert summary["counts"]["missing"] == len(catalog.EVIDENCE_FIELDS)  # unknown = risk

    documents = [
        dict(title="Master services agreement", kind="contract",
             text="Customer data is processed in the UAE region and this data residency commitment is contractual. "
                  "Either party may give 60 days termination notice and data export is provided on exit."),
        dict(title="Launch blog post", kind="marketing",
             text="Qamar Nano scores 91% on our Arabic benchmark. We take fairness seriously."),
    ]
    result = client.post("/models/qamar-nano/versions/1.0/evidence", headers=headers, json={"documents": documents}).json()
    by_field = {c["field"]: c for c in result["changes"]}
    assert by_field["data_residency"]["to"] == "verified"
    assert by_field["exit_terms"]["to"] == "verified"
    assert by_field["benchmark_arabic"]["to"] == "unsupported"   # marketing claim, no method
    assert by_field["fairness_evaluation"]["to"] == "unsupported"
    gaps = {g["field"]: g for g in result["summary"]["gaps"]}
    assert "licence_terms" in gaps and gaps["licence_terms"]["status"] == "missing" and gaps["licence_terms"]["risk"]
    assert "data_residency" not in gaps and "benchmark_arabic" in gaps

    # A weaker document never downgrades evidence already on file.
    weaker = [dict(title="Sales email", kind="email", text="Data residency: hosted in the EU region for now.")]
    again = client.post("/models/qamar-nano/versions/1.0/evidence", headers=headers, json={"documents": weaker}).json()
    assert "data_residency" not in {c["field"] for c in again["changes"]}

    bad_kind = client.post("/models/qamar-nano/versions/1.0/evidence", headers=headers,
                           json={"documents": [dict(title="x", kind="tweet", text="hello")]})
    assert bad_kind.status_code == 422


def test_an_extraction_whose_quote_is_not_in_the_document_is_discarded(client, login, monkeypatch):
    async def invented(document, model_label):
        return evidence_service.Extraction(fields=[evidence_service.ExtractedField(
            field="security_certifications", quote="We hold ISO 27001 certification.", summary="ISO 27001", attributes={})])

    monkeypatch.setattr(evidence_service, "_extract", invented)
    headers = login("saeed.almarri@hrl.gov.example")
    result = client.post("/models/rimal-small/versions/3.2/evidence", headers=headers, json={"documents": [
        dict(title="Brochure", kind="marketing", text="Rimal Small is fast and affordable.")]}).json()
    assert result["changes"] == []
    assert "not in the document" in result["discarded_extractions"][0]["reason"]


def test_new_version_starts_with_no_evidence(client, login):
    assert client.post("/models/rimal-small/versions", headers=login(HR_OFFICER), json={"version": "3.3"}).status_code == 403
    headers = login("saeed.almarri@hrl.gov.example")
    assert client.post("/models/rimal-small/versions", headers=headers, json={"version": "3.3"}).status_code == 201
    versions = {v["version"]: v for v in client.get("/models/rimal-small", headers=headers).json()["versions"]}
    assert versions["3.2"]["status"] == "superseded" and versions["3.3"]["status"] == "current"
    assert len(versions["3.3"]["evidence_gaps"]) == len(catalog.EVIDENCE_FIELDS)


def test_named_person_can_correct_a_field_and_it_is_audited(client, login):
    headers = login("mariam.alhashemi@rid.gov.example")
    updated = client.put("/models/waha-70b/versions/3.3/evidence/incident_disclosure", headers=headers, json=dict(
        status="verified", value={"notify_within_hours": 72}, source="Contract amendment 3", note="Read the signed amendment."))
    assert updated.status_code == 200 and "Mariam Al Hashemi" in updated.json()["note"]
    assert client.get("/audit?action=evidence.corrected", headers=headers).json()[0]["details"]["field"] == "incident_disclosure"


# ───────────── reuse rules (seeded scenarios) ─────────────

def _decision(body, reference):
    return next(d for d in body["reuse_decisions"] if d["source_reference"] == reference)


def test_scenario_a_hr_summariser_fast_track_reuses_hr_policy_assistant(client, login):
    body = client.post("/assessments/preview", headers=login(HR_OFFICER),
                       json={"use_case_code": "HRL-SUMM", "model_slug": "sahab-flash"}).json()
    assert body["risk_tier"] == "low" and body["track"] == "fast"
    decision = _decision(body, "ASM-2026-0001")
    assert decision["selected"] and decision["outcome"] in ("allowed", "partial")
    assert {"hallucination", "prompt_injection", "pii_leakage", "arabic_msa"} <= set(decision["reused_checks"])
    assert "task_accuracy" in decision["rerun_checks"]  # its own test set always runs
    assert _decision(body, "ASM-2026-0002")["outcome"] != "blocked"  # citizen-facing evidence may inform an internal use


def test_scenario_b_residency_partial_reuse_tier_rises_security_reruns(client, login):
    body = client.post("/assessments/preview", headers=login(RID_OFFICER),
                       json={"use_case_code": "RID-SUMM", "model_slug": "sahab-flash", "reuse_from_assessment_id": 1}).json()
    assert body["risk_tier"] == "high"  # passport data
    decision = _decision(body, "ASM-2026-0001")
    assert decision["outcome"] == "partial" and decision["selected"]
    rules = {r["rule"] for r in decision["reasons"]}
    assert {"R4", "R5"} <= rules  # tier rises, data sensitivity rises
    assert set(catalog.SECURITY_PRIVACY_CHECKS) <= set(decision["rerun_checks"])
    assert {"english", "arabic_msa", "hallucination"} <= set(decision["reused_checks"])


def test_scenario_c_social_reuses_traffic_but_people_impact_runs_fresh(client, login):
    body = client.post("/assessments/preview", headers=login(SCS_OFFICER),
                       json={"use_case_code": "SCS-ASSIST", "model_slug": "sahab-flash"}).json()
    decision = _decision(body, "ASM-2026-0002")
    assert decision["selected"] and decision["outcome"] == "partial"
    assert {"accessibility", "contestability", "fairness", "plain_language"} <= set(decision["rerun_checks"])
    assert {"arabic_msa", "arabic_gulf", "prompt_injection", "pii_leakage"} <= set(decision["reused_checks"])
    assert any(r["rule"] == "R7" for r in decision["reasons"])
    assert _decision(body, "ASM-2026-0001")["outcome"] == "blocked"  # HR's internal approval
    assert body["plan"]["inherited_conditions"]  # Traffic's conditions are shown to Social
    assert body["registry_knowledge"]["lessons"] and body["registry_knowledge"]["incidents"]


def test_scenario_d_internal_tool_for_citizen_facing_use_is_blocked(client, login):
    headers = login(SCS_CIVIL)
    request = {"use_case_code": "SCS-POLICY-PUBLIC", "model_slug": "sahab-flash", "reuse_from_assessment_id": 1}
    created = client.post("/assessments", headers=headers, json=request)
    assert created.status_code == 201, created.text
    assessment = created.json()
    assert assessment["status"] == "blocked"
    assert "never transfers directly to a citizen-facing use" in assessment["summary"]["blocked_reason"]
    requested = next(d for d in assessment["reuse_decisions"] if d["requested"])
    assert requested["outcome"] == "blocked" and requested["reasons"][0]["rule"] == "R3" and not requested["selected"]
    assert assessment["check_results"] == []  # nothing was carried over
    audit = client.get(f"/audit?assessment_id={assessment['id']}&action=reuse.decided", headers=headers).json()
    assert any(row["details"]["outcome"] == "blocked" and row["details"]["requested"] for row in audit)


def test_other_versions_and_rejections_are_never_reused(client, login):
    body = client.post("/assessments/preview", headers=login(HR_OFFICER),
                       json={"use_case_code": "HRL-PERMIT", "model_slug": "najm-mini", "version": "1.1"}).json()
    assert all(d["outcome"] == "blocked" and d["reasons"][0]["rule"] == "R1" for d in body["reuse_decisions"])
    assert body["plan"]["counts"]["reused"] == 0

    body = client.post("/assessments/preview", headers=login(HR_OFFICER),
                       json={"use_case_code": "HRL-CV", "model_slug": "waha-70b"}).json()
    assert _decision(body, "ASM-2026-0005")["reasons"][0]["rule"] == "R0"
    assert body["registry_knowledge"]["prior_rejections"][0]["reference"] == "ASM-2026-0005"
    gaps = {g["field"]: g["severity"] for g in body["evidence"]["gaps"]}
    assert gaps["fairness_evaluation"] == "high"


# ───────────── starting an assessment ─────────────

def test_start_assessment_builds_a_plan_and_attaches_reused_evidence(client, login):
    headers = login(RID_OFFICER)
    created = client.post("/assessments", headers=headers,
                          json={"use_case_code": "RID-SUMM", "model_slug": "sahab-flash", "reuse_from_assessment_id": 1})
    assert created.status_code == 201, created.text
    assessment = created.json()
    assert assessment["status"] == "planned" and assessment["risk_tier"] == "high" and assessment["track"] == "full"
    assert assessment["reference"].startswith("ASM-")
    plan = assessment["plan"]
    assert plan["counts"]["reused"] + plan["counts"]["to_run"] == plan["counts"]["required"]
    assert all(item["reason"] for item in plan["run"])

    reused = [c for c in assessment["check_results"] if c["source"] == "reused"]
    assert len(reused) == plan["counts"]["reused"] > 0
    assert all(c["reused_from_assessment_id"] == 1 for c in reused)
    use_case_thresholds = assessment["use_case"]["thresholds"]
    assert all(c["threshold"] == use_case_thresholds.get(c["check_key"]) for c in reused)  # judged against this card
    assert not {c["check_key"] for c in reused} & set(catalog.SECURITY_PRIVACY_CHECKS)

    # Evidence gaps become open concerns for the reviewers.
    assert any(c["raised_by_agent"] == "evidence_registry" and c["status"] == "open" for c in assessment["concerns"])
    assert {t["step_key"] for t in assessment["step_timings"]} == {"intake", "evidence", "reuse_search"}
    actions = {row["action"] for row in client.get(f"/audit?assessment_id={assessment['id']}", headers=headers).json()}
    assert {"assessment.started", "risk_tier.assigned", "reuse.decided", "plan.built"} <= actions


def test_only_the_owning_department_can_start_an_assessment(client, login):
    response = client.post("/assessments", headers=login(HR_OFFICER),
                           json={"use_case_code": "RID-SUMM", "model_slug": "sahab-flash"})
    assert response.status_code == 403


def test_full_reuse_is_allowed_when_the_whole_context_matches(client, login):
    headers = login(HR_OFFICER)
    use_case = client.post("/use-cases", headers=headers, json=dict(
        title="Internal IT policy Q&A assistant", purpose="Answer staff questions about published IT policies.",
        audience_type="internal", affected_users=["employees"], data_sensitivity="internal", consequence_of_error="minor",
        autonomy_level="assistive", human_oversight="sampled", languages=["en", "ar-msa"])).json()
    body = client.post("/assessments/preview", headers=headers,
                       json={"use_case_code": use_case["code"], "model_slug": "sahab-flash"}).json()
    decision = _decision(body, "ASM-2026-0001")
    assert decision["outcome"] == "allowed" and decision["selected"]
    # Even then the department's own checks run: accountability does not transfer.
    assert {"task_accuracy", "human_oversight", "transparency"} <= set(decision["rerun_checks"])
    assert all(catalog.CHECKS[c][0] == "compliance" or c == "task_accuracy" for c in decision["rerun_checks"])
