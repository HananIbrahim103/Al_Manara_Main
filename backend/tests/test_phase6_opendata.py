"""Open data (Bayanat): parsing, case generation, links, evaluation, update detection. Runs after Phases 1-5.

The network is never used here except in the opt-in live test (BAYANAT_LIVE=1).
"""
import asyncio
import io
import os
from datetime import date

import openpyxl
import pytest

from app.services import bayanat, datagen
from app.services.testing import rule_check

ADMIN = "registry.admin@registry.gov.example"
HR_OFFICER, HR_APPROVER = "daniel.okafor@hrl.gov.example", "noura.alketbi@hrl.gov.example"
RID_OFFICER = "ahmed.alnuaimi@rid.gov.example"


# ───────────── parsing the portal (offline) ─────────────

PAGE = """<h1>Traffic accidents by type of accident 2025</h1>
<h6> Entity Name </h6> <span>Ministry Of Interior</span>
<h6> Last Updated Date </h6> <span>01/05/2026</span>
<div class="tag-box"> <img src="x.svg" /> <span>Security and Justice</span> </div>
<div class="col-xl-4 accordion-item" data-item='{"ID":"tok1","NameEN":"Metadata and Data Dictionary","FormatID":70002,"FileURL":"/File/Get/aaa"}'></div>
<div class="col-xl-4 accordion-item" data-item='{"ID":"tok2","NameEN":"Dataset File","FormatID":70002,"FileURL":"/File/Get/bbb","DataResourcePreview":{"Text":"it's quoted"}}'></div>
"""


def _xlsx() -> bytes:
    book = openpyxl.Workbook()
    meta = book.active
    meta.title = "Meta Data"
    meta.append(["Dataset Name_EN", "Traffic accidents"])
    data = book.create_sheet("Data Set")
    data.append(["Ministry of Interior"])  # banner row above the table
    data.append([])
    data.append(["Year", "Type of accident", "Total"])
    for row in [(2025, "صدم وتصادم", 4085), (2025, "تدهور", 800), (2025, "دهس", 1102), (2025, "أخرى", 27), (2025, "المجموع", 6014)]:
        data.append(list(row))
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


def test_dataset_page_is_parsed_including_quotes_inside_the_json():
    page = bayanat.parse_page("abc", PAGE)
    assert page.title.startswith("Traffic accidents") and page.publisher == "Ministry Of Interior"
    assert page.last_updated == date(2026, 5, 1) and page.topics == ["Security and Justice"]
    assert [r.token for r in page.resources] == ["tok1", "tok2"] and page.resources[1].file_ref == "/File/Get/bbb"
    assert bayanat.token_from("https://bayanat.ae/en/Datasets/Dataset-info?id=abc_-1") == "abc_-1"


def test_the_real_table_is_found_under_banner_rows_and_beside_a_metadata_sheet():
    table = bayanat.find_table(_xlsx())
    assert table.sheet == "Data Set" and table.columns == ["Year", "Type of accident", "Total"]
    assert table.measure == "Total" and table.dimensions == ["Type of accident"] and table.total_rows == 5
    assert bayanat.checksum(table) == bayanat.checksum(bayanat.find_table(_xlsx()))
    assert bayanat.find_table(b"%PDF-1.7 ...") is None


# ───────────── generating cases (offline) ─────────────

def _source(rows, measure="Count", dimensions=("Emirate", "Education"), checksum="fixed"):
    return {"title": "Test table", "publisher": "Test ministry", "rows": rows, "measure": measure,
            "dimensions": list(dimensions), "checksum": checksum}


ROWS = [{"Emirate": e, "Education": d, "Count": n} for e, d, n in [
    ("Abu Dhabi", "Diploma", 153), ("Abu Dhabi", "High School", 1316), ("Dubai", "Diploma", 61), ("Dubai", "High School", 852),
    ("Sharjah", "Diploma", 90), ("Sharjah", "High School", 460), ("Ajman", "Diploma", 12), ("Ajman", "High School", 140),
    ("Total", "Diploma", 316), ("Total", "High School", 2768)]]


def test_answers_are_computed_from_the_table_and_totals_are_never_double_counted():
    drafts = datagen.generate(_source(ROWS), ["en", "ar-msa"])
    kinds = {d.kind: d for d in drafts}
    assert {"lookup", "total", "highest", "absent", "lookup_ar"} <= set(kinds)
    assert all("Total |" not in d.prompt for d in drafts)  # the 'Total' row is left out of every excerpt
    assert kinds["highest"].expected == {"must_include": ["Abu Dhabi"], "numbers": ["1469"]}  # 153 + 1316
    assert kinds["total"].expected["numbers"][0] in {"1469", "913", "550", "152"}
    assert kinds["absent"].check_key == "hallucination" and kinds["lookup_ar"].language == "ar-msa"
    assert [d.prompt for d in drafts] == [d.prompt for d in datagen.generate(_source(ROWS), ["en", "ar-msa"])]  # repeatable


def test_percentages_are_never_added_up():
    rows = [{"Region": r, "Gender": g, "Share (percent)": s} for r, g, s in [
        ("Abu Dhabi", "Male", "62.6"), ("Abu Dhabi", "Female", "37.4"), ("Al Ain", "Male", "69.1"), ("Al Ain", "Female", "30.9"),
        ("Al Dhafra", "Male", "80.2"), ("Al Dhafra", "Female", "19.8")]]
    drafts = datagen.generate(_source(rows, "Share (percent)", ("Region", "Gender")), ["en"])
    published = {float(r["Share (percent)"]) for r in rows}
    assert drafts and {d.kind for d in drafts} <= {"lookup", "absent"}
    assert all(float(n) in published for d in drafts for n in d.expected.get("numbers", []))


def test_figures_are_matched_as_whole_numbers():
    assert rule_check("There were 1,316 applications.", {"numbers": ["1316"]}) == []
    assert rule_check("There were 13 applications.", {"numbers": ["3"]}) == ["missing the figure 3"]
    assert rule_check("Not in the table; it was 852.", {"numbers_absent": ["852"], "must_include_any": [["not in the table"]]})


# ───────────── the seeded registry ─────────────

def test_seed_links_real_tables_to_the_use_cases(client, login):
    headers = login(HR_OFFICER)
    sources = {s["key"]: s for s in client.get("/data-sources", headers=headers).json()}
    assert len(sources) == 7 and all(s["portal"] == "bayanat" and s["page_url"].startswith("https://bayanat.ae/") for s in sources.values())
    assert sources["RID-AFFIDAVITS"]["publisher"] == "Ministry of Justice" and sources["RID-AFFIDAVITS"]["use_cases"] == ["RID-SUMM"]
    assert all(s["active_test_cases"] > 0 for s in sources.values())
    detail = client.get("/data-sources/SCS-MARRIAGE-GRANT", headers=headers).json()
    assert detail["sample_rows"] and detail["licence_url"].endswith("Terms-and-conditions")
    assert {c["kind"] for c in detail["test_cases"]} >= {"lookup", "absent"}
    assert {s["key"] for s in client.get("/use-cases/TRF-ASSIST/data-sources", headers=headers).json()} == {"TRF-ACCIDENT-TYPE", "TRF-ACCIDENT-CAUSE"}


def test_evaluation_runs_the_open_data_cases_and_the_record_cites_the_tables(client, login):
    headers = login(RID_OFFICER)
    created = client.post("/assessments", headers=headers, json={"use_case_code": "RID-SUMM", "model_slug": "najm-mini"}).json()
    assert client.post(f"/assessments/{created['id']}/evaluate?wait=true", headers=headers).status_code == 202
    runs = client.get(f"/assessments/{created['id']}/test-runs?check=task_accuracy", headers=headers).json()
    assert any(r["origin"] == "bayanat" for r in runs)
    submitted = client.post(f"/assessments/{created['id']}/submit-for-review", headers=headers).json()
    open_data = submitted["decision_record"]["content"]["evidence_used"]["open_data"]
    assert open_data[0]["key"] == "RID-AFFIDAVITS" and open_data[0]["cases_run"] > 0 and open_data[0]["version"]
    compliance = client.get(f"/assessments/{created['id']}/compliance", headers=headers).json()
    assert "open-data" in next(f for f in compliance if f["rule"] == "SD-2")["note"]


# ───────────── linking ─────────────

def test_only_the_owning_department_links_a_table_and_unlinking_retires_its_cases(client, login):
    body = {"data_source": "SCS-BIRTHS"}
    assert client.post("/use-cases/HRL-POLICY-QA/data-sources", headers=login(RID_OFFICER), json=body).status_code == 403
    linked = client.post("/use-cases/HRL-POLICY-QA/data-sources", headers=login(HR_OFFICER), json=body)
    assert linked.status_code == 201 and linked.json()["test_cases_written"] > 0
    assert client.post("/use-cases/HRL-POLICY-QA/data-sources", headers=login(HR_OFFICER), json=body).status_code == 409
    assert client.delete("/use-cases/HRL-POLICY-QA/data-sources/SCS-BIRTHS", headers=login(HR_OFFICER)).status_code == 204
    cases = client.get("/test-sets/DATA-HRL-POLICY-QA", headers=login(HR_OFFICER)).json()["cases"]
    assert cases and all(c["meta"].get("superseded") for c in cases)


# ───────────── watching the portal for new versions (network faked) ─────────────

def _fake_snapshot(detail: dict, rows: list[dict], last_updated: date) -> bayanat.Snapshot:
    table = bayanat.Table(columns=detail["columns"], rows=rows, measure=detail["measure"], dimensions=detail["dimensions"],
                          total_rows=len(rows))
    page = bayanat.DatasetPage(token="tok", title=detail["title"], publisher=detail["publisher"], last_updated=last_updated,
                               topics=detail["topics"], page_url=detail["page_url"], resources=[])
    resource = bayanat.Resource(token="r", name=detail["resource"]["name"], format_id=70002, file_ref=detail["resource"]["file_ref"])
    return bayanat.Snapshot(page=page, resource=resource, table=table, checksum=bayanat.checksum(table))


def test_a_changed_table_rewrites_cases_and_sends_dependent_deployments_back(client, login, monkeypatch):
    headers = login(ADMIN)
    detail = client.get("/data-sources/HRL-FEDERAL-EMPLOYEES", headers=headers).json()
    full = client.get("/data-sources/HRL-FEDERAL-EMPLOYEES", headers=headers).json()
    rows = full["sample_rows"]  # same columns, fewer rows: a different version of the table
    old_date = date.fromisoformat(detail["last_updated"])
    summariser = client.get("/use-cases/HRL-SUMM", headers=headers).json()["id"]

    def live_deployments() -> set:
        return {d["id"] for d in client.get("/registry/deployments?department=HRL", headers=headers).json()
                if d["use_case_id"] == summariser and d["status"] in ("active", "under_reassessment", "paused")}

    relying = live_deployments()
    if not relying:
        # Run on its own (without the Phase 4 tests) nothing uses the summariser yet: approve it here, playing the named people.
        run = client.post("/scenarios/a/run", headers=login(HR_OFFICER)).json()
        for step in run["human_steps"]:
            if step["request"].startswith("POST /reviews/"):
                assert client.post(step["request"].split(" ")[1], headers=login(step["login_as"]),
                                   json={"status": "no_objection", "comment": "Checked the evidence in my area."}).status_code == 200
        decided = client.post(f"/assessments/{run['assessment_id']}/decision", headers=login(HR_APPROVER),
                              json={"decision": "approved", "reason": "Fast-track checks passed; approved for this test."})
        assert decided.status_code == 200, decided.text
        relying = live_deployments()

    async def same(token, client=None):
        from app.db import SessionLocal
        from app.models import DataSource
        async with SessionLocal() as session:
            ds = await session.get(DataSource, detail["id"])
            table = bayanat.Table(columns=ds.columns, rows=ds.rows, measure=ds.measure, dimensions=ds.dimensions, total_rows=ds.total_rows)
        snap = _fake_snapshot(detail, ds.rows, old_date)
        snap.table, snap.checksum = table, ds.checksum
        return snap

    monkeypatch.setattr(bayanat, "snapshot", same)
    assert client.post("/data-sources/HRL-FEDERAL-EMPLOYEES/refresh", headers=headers).json()["changed"] is False

    async def changed(token, client=None):
        return _fake_snapshot(detail, rows, date(2026, 11, 9))

    monkeypatch.setattr(bayanat, "snapshot", changed)
    assert client.post("/data-sources/HRL-FEDERAL-EMPLOYEES/refresh", headers=login(HR_OFFICER)).status_code == 403
    result = client.post("/data-sources/HRL-FEDERAL-EMPLOYEES/refresh", headers=login(HR_APPROVER)).json()
    assert result["changed"] and result["content_changed"] and result["cases_rewritten"] > 0
    assert result["before"]["rows"] == detail["rows"] and result["after"]["rows"] == len(rows)
    assert relying and set(result["deployments_sent_back"]) == relying  # every live deployment of HR's summariser relies on this table
    after = client.get("/data-sources/HRL-FEDERAL-EMPLOYEES", headers=headers).json()
    assert after["versions_seen"] == 2 and after["last_updated"] == "2026-11-09"
    assert any(c["superseded"] for c in after["test_cases"]) and any(not c["superseded"] for c in after["test_cases"])
    for deployment_id in relying:
        deployment = client.get(f"/deployments/{deployment_id}", headers=headers).json()["deployment"]
        assert deployment["status"] in ("under_reassessment", "paused")
    events = client.get("/lifecycle/events?trigger_type=data_source_change", headers=headers).json()
    assert events and events[0]["payload"]["data_source"] == "HRL-FEDERAL-EMPLOYEES"


def test_unreachable_portal_is_recorded_not_hidden(client, login, monkeypatch):
    async def down(token, client=None):
        raise bayanat.BayanatError("Could not reach Bayanat: timeout")

    monkeypatch.setattr(bayanat, "snapshot", down)
    result = client.post("/data-sources/SCS-BIRTHS/refresh", headers=login(ADMIN)).json()
    assert result["changed"] is False and "timeout" in result["error"]
    assert client.get("/data-sources/SCS-BIRTHS", headers=login(ADMIN)).json()["status"] == "unreachable"


def test_registering_a_dataset_is_for_the_registry_administrator(client, login, monkeypatch):
    detail = client.get("/data-sources/TRF-ACCIDENT-TYPE", headers=login(ADMIN)).json()
    rows = [{"Year": 2025, "Type of accident": t, "Total": n} for t, n in [("a", 1), ("b", 2), ("c", 3), ("d", 4)]]

    async def fake(token, client=None):
        snap = _fake_snapshot({**detail, "columns": ["Year", "Type of accident", "Total"]}, rows, date(2026, 1, 1))
        snap.resource.file_ref = "/File/Get/new-file"
        return snap

    monkeypatch.setattr(bayanat, "snapshot", fake)
    body = {"dataset": "https://bayanat.ae/en/Datasets/Dataset-info?id=xyz", "key": "TEST-NEW"}
    assert client.post("/data-sources", headers=login(HR_APPROVER), json=body).status_code == 403
    created = client.post("/data-sources", headers=login(ADMIN), json=body)
    assert created.status_code == 201 and created.json()["rows"] == 4
    assert client.post("/data-sources", headers=login(ADMIN), json=body).status_code == 409


@pytest.mark.skipif(os.environ.get("BAYANAT_LIVE") != "1", reason="live portal test; set BAYANAT_LIVE=1 to run")
def test_live_portal_still_serves_a_seeded_table():
    from app.seed.opendata import SOURCES
    snap = asyncio.run(bayanat.snapshot(SOURCES[0][1]))
    assert snap.table.total_rows >= 4 and snap.page.publisher
