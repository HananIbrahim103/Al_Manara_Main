"""Phase 5: lifecycle monitor, exit rules, incidents, feedback and metrics. Runs after Phase 4's scenarios."""
ADMIN = "registry.admin@registry.gov.example"
HR_OFFICER, HR_APPROVER = "daniel.okafor@hrl.gov.example", "noura.alketbi@hrl.gov.example"
RID_OFFICER, RID_APPROVER = "ahmed.alnuaimi@rid.gov.example", "khalid.almansoori@rid.gov.example"
TRF_OFFICER, TRF_APPROVER = "salma.alblooshi@trf.gov.example", "sultan.aldhaheri@trf.gov.example"
SCS_OFFICER, SCS_APPROVER = "reem.altunaiji@scs.gov.example", "moza.alremeithi@scs.gov.example"


def deployment_for(client, login, department, use_case_code):
    headers = login(ADMIN)
    use_case = client.get(f"/use-cases/{use_case_code}", headers=headers).json()
    rows = [d for d in client.get(f"/registry/deployments?department={department}", headers=headers).json()
            if d["use_case_id"] == use_case["id"] and d["status"] != "retired"]
    return rows[-1]


def emails(client, login):
    return {u["id"]: u["email"] for u in client.get("/users", headers=login(ADMIN)).json()}


def to_decision(client, login, assessment_id, officer, approver, decision, reason):
    """Evaluate, send for review, play every reviewer, close high concerns, then the approver decides."""
    assert client.post(f"/assessments/{assessment_id}/evaluate?wait=true", headers=login(officer)).status_code == 202
    submitted = client.post(f"/assessments/{assessment_id}/submit-for-review", headers=login(officer))
    assert submitted.status_code == 200, submitted.text
    people = emails(client, login)
    for review in submitted.json()["reviews"]:
        client.post(f"/reviews/{review['id']}", headers=login(people[review["reviewer_id"]]),
                    json={"status": "no_objection", "comment": "Reviewed the reassessment."})
    assessment = client.get(f"/assessments/{assessment_id}", headers=login(officer)).json()
    for concern in assessment["concerns"]:
        if concern["status"] == "open" and concern["severity"] == "high":
            client.post(f"/concerns/{concern['id']}/accept-risk", headers=login(approver), json={"text": "Accepted for this reassessment."})
    body = {"decision": decision, "reason": reason}
    if decision != "rejected":
        body["override_recommendation"] = assessment["recommendation"] == "reject"
    decided = client.post(f"/assessments/{assessment_id}/decision", headers=login(approver), json=body)
    assert decided.status_code == 200, decided.text
    return decided.json()


# ───────────── scenario (e) ─────────────

def test_scenario_e_new_version_alerts_everyone_and_objections_trigger_reassessment(client, login):
    result = client.post("/scenarios/e/run", headers=login(ADMIN))
    assert result.status_code == 200, result.text
    result = result.json()
    assert result["new_version"] == "Sahab Flash 2.1"
    assert result["departments_alerted_about_new_version"] == ["HRL", "RID", "SCS", "TRF"]  # every department using the model
    assert result["complaint_spike"]["spike"] and result["complaint_spike"]["recent"] >= 5
    assert result["traffic_deployment"]["status"] == "under_reassessment"
    assert "Complaints and appeals are rising" in result["traffic_deployment"]["reason"]

    # Pinned deployments keep running on the approved version; only Traffic was sent back.
    hr = deployment_for(client, login, "HRL", "HRL-POLICY-QA")
    assert hr["status"] == "active"
    detail = client.get(f"/deployments/{hr['id']}", headers=login(HR_OFFICER)).json()
    assert detail["alerts"][0]["action_required"] == "reassess" and not [r for r in detail["exit_rules"] if r["rule"] == "X5"]
    events = {e["trigger_type"] for e in client.get("/lifecycle/events", headers=login(HR_OFFICER)).json()}
    assert {"new_model_version", "complaint_spike"} <= events
    assert client.get("/models/sahab-flash", headers=login(HR_OFFICER)).json()["versions"][0]["status"] == "superseded"


def test_rejected_reassessment_pauses_the_deployment(client, login):
    traffic = deployment_for(client, login, "TRF", "TRF-ASSIST")
    assert client.post(f"/deployments/{traffic['id']}/reassess", headers=login(HR_OFFICER), json={}).status_code == 403
    started = client.post(f"/deployments/{traffic['id']}/reassess", headers=login(TRF_OFFICER), json={})
    assert started.status_code == 201, started.text
    reassessment = started.json()
    assert reassessment["reassessment_of_deployment_id"] == traffic["id"]
    assert client.post(f"/deployments/{traffic['id']}/reassess", headers=login(TRF_OFFICER), json={}).status_code == 409
    detail = client.get(f"/assessments/{reassessment['id']}", headers=login(TRF_OFFICER)).json()
    assert detail["model_version"]["version"] == "2.1" and detail["plan"]["counts"]["reused"] == 0  # no evidence crosses versions

    to_decision(client, login, reassessment["id"], TRF_OFFICER, TRF_APPROVER, "rejected",
                "Version 2.1 has no provider evidence yet; objections are rising.")
    after = client.get(f"/deployments/{traffic['id']}", headers=login(TRF_OFFICER)).json()
    assert after["deployment"]["status"] == "paused"
    assert {"X6"} <= {r["rule"] for r in after["exit_rules"]}
    assert client.post(f"/deployments/{traffic['id']}/resume", headers=login(TRF_APPROVER),
                       json={"reason": "Trying to resume after a rejected reassessment."}).status_code == 409
    retired = client.post(f"/deployments/{traffic['id']}/retire", headers=login(TRF_APPROVER),
                          json={"reason": "Reassessment rejected; the service falls back to officers."})
    assert retired.status_code == 200 and retired.json()["status"] == "retired" and retired.json()["retired_at"]


def test_approved_reassessment_replaces_the_deployment(client, login):
    summariser = deployment_for(client, login, "HRL", "HRL-SUMM")
    started = client.post(f"/deployments/{summariser['id']}/reassess", headers=login(HR_OFFICER), json={"version": "2.0"}).json()
    decided = to_decision(client, login, started["id"], HR_OFFICER, HR_APPROVER, "approved",
                          "Same pinned version, re-checked after the new release; still fit for purpose.")
    assert decided["status"] == "approved"
    old = client.get(f"/deployments/{summariser['id']}", headers=login(HR_OFFICER)).json()["deployment"]
    new = deployment_for(client, login, "HRL", "HRL-SUMM")
    assert old["status"] == "retired" and old["replaced_by_deployment_id"] == new["id"] and new["assessment_id"] == started["id"]


# ───────────── incidents, lessons, exit rules ─────────────

def test_high_incident_pauses_until_resolved_and_resumed_and_lesson_is_shared(client, login):
    visas = deployment_for(client, login, "RID", "RID-SUMM")
    assert client.post("/incidents", headers=login(HR_OFFICER), json={
        "deployment_id": visas["id"], "title": "Not our deployment", "description": "Should be refused.", "category": "hallucination", "severity": "low"}).status_code == 403
    incident = client.post("/incidents", headers=login(RID_OFFICER), json={
        "deployment_id": visas["id"], "title": "Summary invented a prior refusal",
        "description": "A file summary mentioned a previous visa refusal that is not in the file.", "category": "hallucination",
        "severity": "high"})
    assert incident.status_code == 201, incident.text
    incident = incident.json()
    detail = client.get(f"/deployments/{visas['id']}", headers=login(RID_OFFICER)).json()
    assert detail["deployment"]["status"] == "paused" and detail["exit_rules"][0]["rule"] == "X1"
    others = client.get("/alerts?department=SCS", headers=login(SCS_OFFICER)).json()
    assert any("Incident with Sahab Flash in another department" in a["title"] and a["action_required"] == "info" for a in others)

    resume = {"reason": "Fix deployed and checked by officers."}
    assert client.post(f"/deployments/{visas['id']}/resume", headers=login(RID_APPROVER), json=resume).status_code == 409
    resolved = client.post(f"/incidents/{incident['id']}/resolve", headers=login(RID_OFFICER), json={
        "root_cause": "The summary prompt allowed background knowledge about typical files.",
        "resolution": "The prompt now forbids facts not in the file; 40 files re-checked.",
        "lesson": {"title": "Summaries must cite only the file", "detail": "Test summaries for facts that are not in the source file.",
                   "tags": ["summarisation"]}})
    assert resolved.status_code == 200 and resolved.json()["status"] == "resolved"
    lessons = client.get("/registry/lessons?model=sahab-flash", headers=login(SCS_OFFICER)).json()
    assert any(lesson["title"] == "Summaries must cite only the file" for lesson in lessons)
    assert client.post(f"/deployments/{visas['id']}/resume", headers=login(RID_OFFICER), json=resume).status_code == 403
    resumed = client.post(f"/deployments/{visas['id']}/resume", headers=login(RID_APPROVER), json=resume)
    assert resumed.status_code == 200 and resumed.json()["status"] == "active"


def test_performance_drift_reassesses_then_pauses(client, login):
    social = deployment_for(client, login, "SCS", "SCS-ASSIST")
    threshold = client.get("/use-cases/SCS-ASSIST", headers=login(SCS_OFFICER)).json()["thresholds"]["task_accuracy"]
    url = f"/deployments/{social['id']}/performance"
    fine = client.post(url, headers=login(SCS_OFFICER), json={"check_key": "task_accuracy", "observed_score": 1.0, "sample_size": 200}).json()
    assert fine["drift"] is False
    small = client.post(url, headers=login(SCS_OFFICER), json={"check_key": "task_accuracy", "observed_score": threshold - 0.03, "sample_size": 200}).json()
    assert small["drift"] and client.get(f"/deployments/{social['id']}", headers=login(SCS_OFFICER)).json()["deployment"]["status"] == "under_reassessment"
    client.post(url, headers=login(SCS_OFFICER), json={"check_key": "task_accuracy", "observed_score": threshold - 0.25, "sample_size": 200})
    detail = client.get(f"/deployments/{social['id']}", headers=login(SCS_OFFICER)).json()
    assert detail["deployment"]["status"] == "paused" and "X3" in detail["deployment"]["status_reason"]
    assert client.post(url, headers=login(SCS_OFFICER), json={"check_key": "cost", "observed_score": 0.5, "sample_size": 1}).status_code == 422


def test_condition_breach_sends_back_and_marks_compliance_at_risk(client, login):
    permits = deployment_for(client, login, "HRL", "HRL-PERMIT")
    url = f"/deployments/{permits['id']}/conditions/1"
    assert client.post(url, headers=login(RID_OFFICER), json={"status": "met", "note": "Not my department."}).status_code == 403
    met = client.post(f"/deployments/{permits['id']}/conditions/0", headers=login(HR_OFFICER),
                      json={"status": "met", "note": "Checked 50 flags: every one confirmed by an officer."}).json()
    assert met["condition_status"][0]["status"] == "met" and met["status"] == "active"
    breached = client.post(url, headers=login(HR_OFFICER), json={"status": "breached", "note": "No sample audit for three weeks."}).json()
    assert breached["status"] == "under_reassessment" and breached["compliance_status"] == "at_risk"
    assert client.post(f"/deployments/{permits['id']}/conditions/9", headers=login(HR_OFFICER),
                       json={"status": "met", "note": "No such condition."}).status_code == 404


def test_provider_terms_change_alerts_every_user_of_the_model(client, login):
    body = {"trigger_type": "provider_terms_change", "model_slug": "najm-mini",
            "description": "Provider B now keeps prompts for 30 days for abuse monitoring."}
    assert client.post("/lifecycle/events", headers=login(RID_APPROVER), json=body).status_code == 403
    result = client.post("/lifecycle/events", headers=login(ADMIN), json=body)
    assert result.status_code == 201 and len(result.json()["alerts"]) == 2
    extract = deployment_for(client, login, "RID", "RID-EXTRACT")
    assert extract["status"] == "under_reassessment" and extract["compliance_status"] == "at_risk"
    change = {"trigger_type": "autonomy_increase", "deployment_id": extract["id"], "description": "Plan to let the AI clear matching files without an officer."}
    assert client.post("/lifecycle/events", headers=login(HR_OFFICER), json=change).status_code == 403
    assert client.post("/lifecycle/events", headers=login(RID_OFFICER), json=change).status_code == 201


def test_quarterly_check_and_scan(client, login):
    assert client.post("/lifecycle/quarterly-check", headers=login(RID_APPROVER)).status_code == 403
    result = client.post("/lifecycle/quarterly-check", headers=login(ADMIN)).json()
    assert result["results"] and all(r["after"] in ("compliant", "at_risk", "non_compliant") and r["rules_checked"] and len(r["note"]) > 20 for r in result["results"])
    assert client.post("/lifecycle/scan", headers=login(HR_OFFICER)).status_code == 403
    scan = client.post("/lifecycle/scan", headers=login(HR_APPROVER))
    assert scan.status_code == 200 and set(scan.json()) == {"complaint_spikes", "overdue_reviews", "exit_recommendations"}


def test_alerts_are_acted_on_by_their_own_department(client, login):
    alert = client.get("/alerts?mine=true", headers=login(HR_OFFICER)).json()[0]
    assert client.post(f"/alerts/{alert['id']}/acknowledge", headers=login(RID_OFFICER), json={"reason": "Not ours to acknowledge."}).status_code == 403
    acknowledged = client.post(f"/alerts/{alert['id']}/acknowledge", headers=login(HR_OFFICER), json={"reason": "Seen; we stay pinned."}).json()
    assert acknowledged["status"] == "acknowledged" and acknowledged["acknowledged_at"]
    closed = client.post(f"/alerts/{alert['id']}/close", headers=login(HR_APPROVER), json={"reason": "Reassessment scheduled."}).json()
    assert closed["status"] == "closed"
    assert client.post(f"/alerts/{alert['id']}/close", headers=login(HR_APPROVER), json={"reason": "Closing twice."}).status_code == 409


def test_feedback_is_recorded_by_the_running_department(client, login):
    visas = deployment_for(client, login, "RID", "RID-SUMM")
    body = {"deployment_id": visas["id"], "source": "frontline_staff", "text": "Summaries save time on sponsor letters."}
    assert client.post("/feedback", headers=login(SCS_OFFICER), json=body).status_code == 403
    recorded = client.post("/feedback", headers=login(RID_OFFICER), json=body)
    assert recorded.status_code == 201 and recorded.json()["complaint_spike"] is None


# ───────────── metrics ─────────────

def test_metrics_report_time_saved_and_compliance_from_recorded_data(client, login):
    metrics = client.get("/metrics", headers=login(HR_OFFICER)).json()
    live = metrics["time_saved"]["this_system"]
    assert live["assessments"] >= 4 and live["manual_hours"] > 0
    assert live["time_saved"] is not None and live["time_saved"] >= 0.8  # in tests the human steps take seconds
    history = metrics["time_saved"]["seeded_history"]
    assert history["assessments"] == 5 and history["time_saved"] >= 0.8 and history["target_met"]  # working hours: about 83%
    assert 0 < history["elapsed_clock"]["time_saved"] < history["time_saved"]  # conservative reading: about 49%
    for row in metrics["time_saved"]["per_assessment"]:
        assert row["system_hours"] < row["manual_hours"] and row["steps_measured"]
    scenario_a = next(r for r in metrics["time_saved"]["per_assessment"] if not r["seeded_history"] and r["track"] == "fast")
    assert scenario_a["reviews_parallel"]["elapsed_s"] <= scenario_a["reviews_parallel"]["sum_of_reviews_s"]

    compliance = metrics["compliance"]
    rows = compliance["per_deployment"]
    assert compliance["deployments"] == len(rows) and compliance["compliant"] == sum(r["compliance_status"] == "compliant" for r in rows)
    assert compliance["rate"] == round(compliance["compliant"] / len(rows), 4)
    assert compliance["target_met"] is False  # breaches and the terms change above are not hidden
    assert all(r["status"] != "retired" for r in rows)
    assert metrics["operations"]["llm_mode"] == "mock"
