"""Phase 4: reviews in parallel, concerns, decision record and the human decision.

Scenarios (a)-(d) run end to end here. The tests play the named people by logging in as each of them,
exactly as they would through the API. The application itself never answers a review or decides.
"""
import re
from pathlib import Path

HR_OFFICER, HR_PERMITS, HR_APPROVER = "daniel.okafor@hrl.gov.example", "hessa.alshamsi@hrl.gov.example", "noura.alketbi@hrl.gov.example"
HR_SECURITY = "saeed.almarri@hrl.gov.example"
RID_OFFICER, RID_APPROVER, RID_CISO = "ahmed.alnuaimi@rid.gov.example", "khalid.almansoori@rid.gov.example", "omar.alsuwaidi@rid.gov.example"
SCS_OFFICER, SCS_CIVIL, SCS_APPROVER = "reem.altunaiji@scs.gov.example", "joseph.mathew@scs.gov.example", "moza.alremeithi@scs.gov.example"
TRF_APPROVER = "sultan.aldhaheri@trf.gov.example"
_DECISION = {"approve": "approved", "approve_with_conditions": "approved_with_conditions", "reject": "rejected"}


def answer_reviews(client, login, result, status="no_objection"):
    for step in result["human_steps"]:
        if step["request"].startswith("POST /reviews/"):
            body = {"status": status, "comment": "Checked the evidence in my area."}
            response = client.post(step["request"].split(" ")[1], headers=login(step["login_as"]), json=body)
            assert response.status_code == 200, response.text


def close_high_concerns(client, login, assessment, approver):
    for concern in assessment["concerns"]:
        if concern["status"] == "open" and concern["severity"] == "high":
            response = client.post(f"/concerns/{concern['id']}/accept-risk", headers=login(approver),
                                   json={"text": "Accepted: the deployment conditions cover this risk."})
            assert response.status_code == 200, response.text


def read(client, login, assessment_id):
    return client.get(f"/assessments/{assessment_id}", headers=login(HR_OFFICER)).json()


# ───────────── scenario (a): fast track, recorded human decision ─────────────

def test_scenario_a_ends_in_a_recorded_human_decision(client, login):
    result = client.post("/scenarios/a/run", headers=login(HR_OFFICER))
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["status"] == "in_review" and result["track"] == "fast"
    assert result["recommendation"]["value"] == "approve"
    assert [r["role"] for r in result["reviewers"]] == ["business_owner", "security"]  # fast track: 2 reviewers
    assessment_id = result["assessment_id"]

    # Nobody can decide while reviews are open, and the system has not decided anything.
    assert client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER),
                       json={"decision": "approved", "reason": "Looks fine to me."}).status_code == 409
    assessment = read(client, login, assessment_id)
    assert assessment["approval"] is None and assessment["status"] == "in_review"
    reviews = assessment["reviews"]
    assert len({r["assigned_at"] for r in reviews}) == 1  # sent at the same time
    assert all(r["selection_reason"] and r["round"] == 1 for r in reviews)

    answer_reviews(client, login, result)
    assessment = read(client, login, assessment_id)
    assert assessment["status"] == "awaiting_decision"
    close_high_concerns(client, login, assessment, HR_APPROVER)

    decided = client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER),
                          json={"decision": "approved", "reason": "Low-risk internal summariser; every fast-track check passed."})
    assert decided.status_code == 200, decided.text
    decided = decided.json()
    assert decided["status"] == "approved" and decided["completed_at"]
    approver_id = client.get("/auth/me", headers=login(HR_APPROVER)).json()["id"]
    assert decided["approval"]["approver_id"] == approver_id and decided["approval"]["risk_accepted_by_id"] == approver_id
    record = decided["decision_record"]
    assert record["content"]["decision"]["by"] == "Noura Al Ketbi"
    for key in ("assumptions", "limitations", "evidence_used", "conditions", "residual_risk", "accountable_owner"):
        assert key in record["content"]
    assert any("mock mode" in item for item in record["content"]["limitations"])  # honest about where scores come from
    assert {"review", "approval", "decision_record"} <= {t["step_key"] for t in decided["step_timings"]}

    deployments = client.get("/registry/deployments?department=HRL", headers=login(HR_OFFICER)).json()
    deployment = next(d for d in deployments if d["assessment_id"] == assessment_id)
    assert deployment["status"] == "active" and deployment["conditions"] == []

    audit = client.get(f"/audit?assessment_id={assessment_id}&action=decision.recorded", headers=login(HR_OFFICER)).json()
    assert audit[0]["actor_type"] == "user" and audit[0]["actor_id"] == str(approver_id)


def test_only_the_named_approver_of_the_owning_department_decides(client, login):
    result = client.post("/scenarios/a/run", headers=login(HR_OFFICER)).json()
    answer_reviews(client, login, result)
    url = f"/assessments/{result['assessment_id']}/decision"
    body = {"decision": "approved", "reason": "Trying to approve without the authority."}
    for someone in (HR_OFFICER, HR_SECURITY, RID_APPROVER, TRF_APPROVER, "registry.admin@registry.gov.example"):
        assert client.post(url, headers=login(someone), json=body).status_code == 403, someone
    assert client.post(url, headers=login(HR_APPROVER), json={"decision": "approved", "reason": "short"}).status_code == 422
    assert client.post(url, headers=login(HR_APPROVER), json={"decision": "rejected", "reason": "Not needed after all."}).status_code == 200
    assert client.post(url, headers=login(HR_APPROVER), json=body).status_code == 409  # one decision per assessment


def test_no_code_path_creates_an_approval_except_the_human_decision():
    """Structural guard: Approval rows are only built in governance.decide (and in the seed's history)."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    builders = sorted(str(p.relative_to(app_dir)) for p in app_dir.rglob("*.py") if re.search(r"(?<!class )\bApproval\(", p.read_text()))
    assert builders == ["seed/__main__.py", "services/governance.py"], builders
    governance_source = (app_dir / "services" / "governance.py").read_text()
    assert governance_source.count("Approval(") == 1
    decide = governance_source.split("async def decide(")[1].split("\nasync def ")[0]
    assert "_require_approver(user, assessment" in decide and "Approval(" in decide


# ───────────── scenario (b): reuse of (a), tier rises, conditions ─────────────

def test_scenario_b_reuses_hr_summariser_and_is_approved_with_conditions(client, login):
    result = client.post("/scenarios/b/run", headers=login(RID_OFFICER)).json()
    assert result["status"] == "in_review" and result["risk_tier"] == "high" and result["track"] == "full"
    assert "scenario a" in result["reuse"]
    assessment = read(client, login, result["assessment_id"])
    source = assessment["plan"]["source"]
    hr_summariser = client.get(f"/assessments/{source['assessment_id']}", headers=login(RID_OFFICER)).json()
    assert hr_summariser["use_case"]["code"] == "HRL-SUMM" and source["outcome"] == "partial"
    assert len(result["reviewers"]) == 4  # full track: every reviewer in the department
    assert result["recommendation"]["value"] == "approve_with_conditions"
    conditions = [c["condition"] for c in result["suggested_conditions"]]
    assert any("officer verifies" in c for c in conditions)

    # A reviewer objects: that becomes a high concern routed to them and blocks approval.
    steps = {s["role"]: s for s in result["human_steps"] if s.get("role")}
    objection = client.post(steps["data_protection"]["request"].split(" ")[1], headers=login(steps["data_protection"]["login_as"]),
                            json={"status": "objection", "comment": "Passport numbers must be masked before any model call."})
    assert objection.status_code == 200
    for role in ("business_owner", "security", "legal"):
        client.post(steps[role]["request"].split(" ")[1], headers=login(steps[role]["login_as"]),
                    json={"status": "no_objection", "comment": "Reviewed; conditions are adequate."})
    assessment = read(client, login, result["assessment_id"])
    assert assessment["status"] == "awaiting_decision"
    objection_concern = next(c for c in assessment["concerns"] if c["raised_by_id"] and c["severity"] == "high")
    blocked = client.post(f"/assessments/{assessment['id']}/decision", headers=login(RID_APPROVER),
                          json={"decision": "approved_with_conditions", "reason": "Conditions cover the residual risk."})
    assert blocked.status_code == 409 and objection_concern["id"] in [c["id"] for c in blocked.json()["detail"]["open_high_concerns"]]

    # Only the person responsible, the raiser or the approver may resolve it; a reviewer from elsewhere may not.
    assert client.post(f"/concerns/{objection_concern['id']}/resolve", headers=login(HR_SECURITY),
                       json={"text": "Not my department."}).status_code == 403
    assert client.post(f"/concerns/{objection_concern['id']}/accept-risk", headers=login(RID_CISO),
                       json={"text": "Only the approver may accept risk."}).status_code == 403
    resolved = client.post(f"/concerns/{objection_concern['id']}/resolve", headers=login(steps["data_protection"]["login_as"]),
                           json={"text": "Masking condition added; verified in the PII leakage test."})
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    close_high_concerns(client, login, read(client, login, assessment["id"]), RID_APPROVER)

    # A risk owner from another department is refused; the department CISO is accepted.
    body = {"decision": "approved_with_conditions", "reason": "Officer verification and masking make the residual risk acceptable.",
            "risk_accepted_by_email": HR_SECURITY}
    assert client.post(f"/assessments/{assessment['id']}/decision", headers=login(RID_APPROVER), json=body).status_code == 422
    body["risk_accepted_by_email"] = RID_CISO
    body["conditions"] = conditions + ["Passport numbers are masked before any model call."]
    decided = client.post(f"/assessments/{assessment['id']}/decision", headers=login(RID_APPROVER), json=body)
    assert decided.status_code == 200, decided.text
    decided = decided.json()
    ciso_id = client.get("/auth/me", headers=login(RID_CISO)).json()["id"]
    assert decided["status"] == "approved_with_conditions" and decided["approval"]["risk_accepted_by_id"] == ciso_id
    deployment = next(d for d in client.get("/registry/deployments?department=RID", headers=login(RID_OFFICER)).json()
                      if d["assessment_id"] == decided["id"])
    assert any("masked before any model call" in c for c in deployment["conditions"])
    assert all(entry["status"] == "unverified" for entry in deployment["condition_status"])


# ───────────── scenario (c): Traffic's evidence, people-impact fresh ─────────────

def test_scenario_c_social_is_approved_with_inherited_conditions(client, login):
    result = client.post("/scenarios/c/run", headers=login(SCS_OFFICER)).json()
    assert result["status"] == "in_review"
    assessment = read(client, login, result["assessment_id"])
    assert assessment["plan"]["source"]["reference"] == "ASM-2026-0002"
    roles = {r["reviewer_role"] for r in assessment["reviews"]}
    assert {"accessibility", "legal_contestability"} <= roles
    answer_reviews(client, login, result)
    close_high_concerns(client, login, read(client, login, assessment["id"]), SCS_APPROVER)
    decision = _DECISION[assessment["recommendation"]]
    decided = client.post(f"/assessments/{assessment['id']}/decision", headers=login(SCS_APPROVER),
                          json={"decision": decision, "reason": "Accessibility and contestability ran fresh and passed; conditions apply."})
    assert decided.status_code == 200, decided.text
    record = decided.json()["decision_record"]["content"]
    assert any(c["source"].startswith("inherited:ASM-2026-0002") for c in record["conditions"])


# ───────────── scenario (d): blocked, nothing to decide ─────────────

def test_scenario_d_is_blocked_with_its_reason(client, login):
    result = client.post("/scenarios/d/run", headers=login(SCS_CIVIL)).json()
    assert result["status"] == "blocked" and result["human_steps"] == []
    assert "never transfers directly to a citizen-facing use" in result["blocked_reason"]
    assert client.post(f"/assessments/{result['assessment_id']}/submit-for-review", headers=login(SCS_CIVIL)).status_code == 409


def test_scenarios_are_run_by_the_owning_department(client, login):
    assert client.post("/scenarios/a/run", headers=login(RID_OFFICER)).status_code == 403
    assert client.post("/scenarios/e/run", headers=login(HR_OFFICER)).status_code == 403
    assert client.post("/scenarios/z/run", headers=login(HR_OFFICER)).status_code == 404
    assert [s["key"] for s in client.get("/scenarios", headers=login(HR_OFFICER)).json()] == list("abcde")


# ───────────── recommendation, overrides, send-back ─────────────

def _evaluated(client, login, officer, use_case, model):
    headers = login(officer)
    created = client.post("/assessments", headers=headers, json={"use_case_code": use_case, "model_slug": model}).json()
    assert client.post(f"/assessments/{created['id']}/evaluate?wait=true", headers=headers).status_code == 202
    return created["id"]


def test_failed_checks_mean_reject_and_approving_needs_an_explicit_override(client, login):
    assessment_id = _evaluated(client, login, HR_PERMITS, "HRL-CV", "waha-70b")
    submitted = client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(HR_PERMITS)).json()
    assert submitted["recommendation"] == "reject"
    assert len(submitted["reviews"]) == 4  # high tier, full track
    # Agent concerns are routed to the reviewer who owns the area.
    fairness = next(r for r in submitted["reviews"] if r["reviewer_role"] == "fairness")
    assert any(c["assigned_to_id"] == fairness["reviewer_id"] for c in submitted["concerns"] if c["area"] in ("fairness", "critic_review"))
    for review in submitted["reviews"]:
        user = client.get("/users", headers=login(HR_APPROVER)).json()
        email = next(u["email"] for u in user if u["id"] == review["reviewer_id"])
        client.post(f"/reviews/{review['id']}", headers=login(email), json={"status": "no_objection", "comment": "Seen the failures."})
    assessment = read(client, login, assessment_id)
    close_high_concerns(client, login, assessment, HR_APPROVER)
    body = {"decision": "approved_with_conditions", "reason": "We need it despite the failures.", "conditions": ["Human re-ranks every list."]}
    refused = client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER), json=body)
    assert refused.status_code == 409 and "override_recommendation" in refused.text
    rejected = client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER),
                           json={"decision": "rejected", "reason": "Fairness across nationalities is below the threshold."}).json()
    assert rejected["status"] == "rejected" and rejected["approval"]["risk_accepted_by_id"] is None
    assert not [d for d in client.get("/registry/deployments", headers=login(HR_OFFICER)).json() if d["assessment_id"] == assessment_id]


def test_rejecting_is_possible_with_open_concerns_but_approving_is_not(client, login):
    assessment_id = _evaluated(client, login, HR_PERMITS, "HRL-CV", "waha-70b")
    client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(HR_PERMITS))
    assessment = read(client, login, assessment_id)
    users = {u["id"]: u["email"] for u in client.get("/users", headers=login(HR_APPROVER)).json()}
    for review in assessment["reviews"]:
        client.post(f"/reviews/{review['id']}", headers=login(users[review["reviewer_id"]]),
                    json={"status": "concerns", "comment": "See my concern about ranking by nationality."})
    approve = {"decision": "approved_with_conditions", "reason": "Override attempt.", "override_recommendation": True, "conditions": ["x" * 10]}
    assert client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER), json=approve).status_code == 409
    assert client.post(f"/assessments/{assessment_id}/decision", headers=login(HR_APPROVER),
                       json={"decision": "rejected", "reason": "Open concerns are not resolved."}).status_code == 200


def test_send_back_withdraws_reviews_and_a_new_round_follows(client, login):
    assessment_id = _evaluated(client, login, HR_OFFICER, "HRL-POLICY-QA", "sahab-flash")
    first = client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(HR_OFFICER)).json()
    assert client.post(f"/assessments/{assessment_id}/send-back", headers=login(HR_SECURITY),
                       json={"reason": "Only the approver can send it back."}).status_code == 403
    sent = client.post(f"/assessments/{assessment_id}/send-back", headers=login(HR_APPROVER),
                       json={"reason": "Re-run with the updated policy test set."}).json()
    assert sent["status"] == "sent_back" and all(r["status"] == "withdrawn" for r in sent["reviews"])
    review_id = first["reviews"][0]["id"]
    assert client.post(f"/reviews/{review_id}", headers=login(HR_APPROVER), json={"status": "no_objection", "comment": "Too late."}).status_code == 409
    assert client.post(f"/assessments/{assessment_id}/evaluate?wait=true", headers=login(HR_OFFICER)).status_code == 202
    second = client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(HR_OFFICER)).json()
    assert {r["round"] for r in second["reviews"]} == {1, 2}
    records = client.get(f"/assessments/{assessment_id}/decision-record/versions", headers=login(HR_OFFICER)).json()
    assert [r["version"] for r in records] == [1, 2]


def test_review_permissions_and_inboxes(client, login):
    assessment_id = _evaluated(client, login, HR_OFFICER, "HRL-POLICY-QA", "sahab-flash")
    client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(HR_OFFICER))
    inbox = client.get("/reviews/inbox", headers=login(HR_SECURITY)).json()
    mine = next(item for item in inbox if item["assessment_id"] == assessment_id)
    assert mine["why_you"] and "prompt_injection" in mine["responsibilities"]
    assert client.post(f"/reviews/{mine['review_id']}", headers=login(HR_APPROVER),
                       json={"status": "no_objection", "comment": "Answering someone else's review."}).status_code == 403
    approvals = client.get("/approvals/inbox", headers=login(HR_APPROVER)).json()
    assert any(a["assessment_id"] == assessment_id and a["pending_reviews"] == 2 for a in approvals)
    assert client.get("/approvals/inbox", headers=login(HR_OFFICER)).json() == []
    raised = client.post(f"/assessments/{assessment_id}/concerns", headers=login(HR_SECURITY),
                         json={"title": "Prompt injection through pasted policy text", "severity": "high", "area": "prompt_injection"})
    assert raised.status_code == 201 and raised.json()["assigned_to_id"] is not None
    assert client.post(f"/assessments/{assessment_id}/concerns", headers=login(RID_CISO),
                       json={"title": "Outsider concern", "severity": "low"}).status_code == 403
