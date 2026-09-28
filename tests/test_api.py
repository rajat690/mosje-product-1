"""API tests (FastAPI TestClient). Order matters only through the session fixtures in conftest."""
from conftest import H


def test_health_needs_no_key(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_docs_available(client):
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    for p in ("/health", "/cbse/students", "/jan-aadhaar/candidates", "/schemes", "/pipeline/run", "/results/funnel",
              "/results/scenarios", "/results/match-outcomes", "/results/scenarios-36",
              "/student/{student_id}/eligible-schemes", "/outreach/queue", "/admin/seed"):
        assert p in spec["paths"], p


def test_auth_required(client):
    assert client.get("/schemes").status_code == 401
    assert client.get("/schemes", headers={"X-API-Key": "wrong"}).status_code == 401
    assert client.post("/admin/seed").status_code == 401


def test_results_404_before_any_run(client, seeded):
    from db.engine import get_engine
    from sqlalchemy import text
    with get_engine().connect() as c:
        runs = c.execute(text("SELECT COUNT(*) FROM pipeline_runs WHERE status='SUCCEEDED'")).scalar()
    if runs == 0:
        assert client.get("/results/funnel", headers=H).status_code == 404


def test_seed_counts_and_idempotent(client, seeded):
    assert seeded["counts"]["jan_aadhaar_members"] > 20000 or seeded["status"] == "skipped"
    r = client.post("/admin/seed", headers=H).json()
    assert r["status"] == "skipped"
    assert r["counts"]["cbse_results"] == 5000 and r["counts"]["scheme_rules"] == 547


def test_cbse_students_paging_and_filters(client, seeded):
    r = client.get("/cbse/students", params={"class": "XII", "year": "2025-26", "page": 2, "page_size": 25}, headers=H)
    d = r.json()
    assert r.status_code == 200 and d["total"] == 2000 and len(d["items"]) == 25 and d["page"] == 2
    assert all(i["class_passed"] == "XII" for i in d["items"])
    assert client.get("/cbse/students", params={"class": "X"}, headers=H).json()["total"] == 3000
    assert client.get("/cbse/students", params={"class": "IX"}, headers=H).status_code == 422
    assert client.get("/cbse/students", params={"year": "1999-00"}, headers=H).json()["total"] == 0


def test_ja_candidates_blocking(client, seeded):
    m = client.get("/jan-aadhaar/members/M0000001", headers=H).json()
    r = client.get("/jan-aadhaar/candidates", params={"dob": m["dob_raw"], "gender": m["gender"]}, headers=H).json()
    assert r["dob_normalised"] == m["dob_iso"]
    ids = [c["member_id"] for c in r["items"]]
    assert "M0000001" in ids
    assert all(c["dob_iso"] == m["dob_iso"] and c["gender_norm"] == m["gender_norm"] for c in r["items"])
    r2 = client.get("/jan-aadhaar/candidates", params={"dob": m["dob_iso"], "district": m["district"]}, headers=H).json()
    assert "M0000001" in [c["member_id"] for c in r2["items"]]
    assert client.get("/jan-aadhaar/candidates", params={"dob": "not a date"}, headers=H).status_code == 422
    assert client.get("/jan-aadhaar/candidates", headers=H).status_code == 422


def test_schemes(client, seeded):
    d = client.get("/schemes", params={"page_size": 1000}, headers=H).json()
    assert d["total"] == 547
    c = client.get("/schemes", params={"level": "Central", "active": True, "page_size": 1000}, headers=H).json()
    assert c["total"] == 44 and all(s["Scheme_Level"] == "Central" and s["Active_Status"] == "ACTIVE" for s in c["items"])
    rj = client.get("/schemes", params={"state": "Rajasthan", "active": True}, headers=H).json()
    assert rj["total"] == 23


def test_pipeline_matches_prototype_headlines(client, run):
    assert run["status"] == "SUCCEEDED"
    f = client.get("/results/funnel", headers=H).json()
    fv = {x["Stage"]: x["Count"] for x in f["funnel"]}
    assert fv["Exact matches (unique, all 5 fields after L1)"] == 2623
    assert fv["Auto-linked (Scenarios 1-3)"] == 3471
    assert fv["Auto-linked + flag (Scenarios 4-6)"] == 241
    assert fv["G7 margin failures (would have linked)"] == 48
    assert fv["Probable - Discovery (overall 70-89.99)"] == 141
    assert fv["Eligibility-checked (linked students)"] == 3712
    q = f["quality"][0]
    assert (q["True_Matches_TP"], q["False_Matches_FP"], q["Missed_Matches_FN"], q["True_Negatives_TN"]) == (3712, 0, 538, 750)
    assert f["eligibility_stats"]["audit_pairs"] == 248704


def test_scenarios_endpoint(client, run):
    d = client.get("/results/scenarios", headers=H).json()
    rows = {r["Scenario"]: r for r in d["rows"]}
    assert len(rows) == 59 and d["summary"]["unreachable"] == 27
    assert rows["EXACT"]["TP"] == 2623 and rows["8"]["FN"] == 226 and rows["NO_CANDIDATE"]["Records"] == 72
    assert rows["20"]["Status"] == "Unreachable"
    t = d["summary"]["totals"]
    assert t["Records"] == 5000 and t["TP"] + t["FP"] == 3712 and t["G7_Blocked"] == 48


def test_match_outcomes_endpoint(client, run):
    assert client.get("/results/match-outcomes").status_code == 401
    assert client.get("/results/match-outcomes", headers={"X-API-Key": "wrong"}).status_code == 401
    d = client.get("/results/match-outcomes", headers=H).json()
    labels = [o["Outcome"] for o in d["outcomes"]]
    assert labels == ["True matches found", "False matches", "Missed matches", "Precision", "Recall",
                      "False-positive rate"]
    v = {o["Key"]: o for o in d["outcomes"]}
    assert (v["true_matches"]["Value"], v["false_matches"]["Value"], v["missed_matches"]["Value"]) == (3712, 0, 538)
    assert v["precision"]["Display"] == "1.000" and v["recall"]["Display"] == "0.873"
    assert v["false_positive_rate"]["Display"] == "0.000"
    assert all(o["Definition"] and o["Formula"] for o in d["outcomes"])
    assert "all links" in v["precision"]["Definition"]
    assert d["counts"] == {"records": 5000, "records_with_true_ja_member": 4250, "TP": 3712, "FP": 0, "FN": 538,
                           "TN": 750}
    q = client.get("/results/funnel", headers=H).json()["quality"][0]
    assert v["recall"]["Value"] == q["Recall"] and d["run_id"]


def test_scenarios_36_endpoint(client, run):
    assert client.get("/results/scenarios-36").status_code == 401
    d = client.get("/results/scenarios-36", headers=H).json()
    rows = {r["#"]: r for r in d["rows"]}
    assert len(d["rows"]) == 38 and [str(i) for i in range(1, 37)] == [r["#"] for r in d["rows"][:36]]
    assert list(d["rows"][0].keys())[:9] == ["#", "Overall Score", "Candidate Name", "DOB", "Father Name",
                                             "Mother Name", "Gender", "Classification", "Action"]
    t = d["summary"]["totals"]
    assert t["Records"] == 5000 and t["True matches (correct link)"] == 3712 and t["Missed matches"] == 538
    assert t["False matches (wrong link)"] == 0 and t["Correctly not linked"] == 750 and t["G7-blocked"] == 48
    assert rows["1"]["of which exact path"] == 2623 and rows["NO_CANDIDATE"]["Records"] == 72
    assert rows["20"]["Status"] == "Unreachable" and rows["20"]["Records"] == 0
    assert rows["6"]["Action differs from V3.0 (records)"] >= 1


def test_outreach_queue_types(client, run):
    e = client.get("/outreach/queue", params={"type": "eligible", "page_size": 1}, headers=H).json()
    dsc = client.get("/outreach/queue", params={"type": "discovery", "page_size": 1}, headers=H).json()
    assert e["total"] == 3712 and dsc["total"] == 141
    assert dsc["items"][0]["Outreach_Status"] == "QUEUE_FOR_DISCOVERY_OUTREACH"
    assert client.get("/outreach/queue", params={"type": "x"}, headers=H).status_code == 422


def test_student_eligible_schemes(client, run):
    d = client.get("/results/decisions", params={"band": "MATCHED", "page_size": 1}, headers=H).json()
    assert d["total"] == 3712
    roll = d["items"][0]["Roll_No"]
    s = client.get(f"/student/{roll}/eligible-schemes", headers=H).json()
    assert s["linkage_band"] == "MATCHED"
    assert len(s["schemes"]) == s["summary"]["Eligible_Scheme_Count"] >= 1
    assert all(x["final_result"] == "ELIGIBLE" and x["Scheme_Name"] for x in s["schemes"])
    full = client.get(f"/student/{roll}/eligible-schemes", params={"include_failed": True}, headers=H).json()
    assert len(full["schemes"]) == s["summary"]["Total_Candidate_Schemes_Checked"]
    nl = client.get("/results/decisions", params={"band": "NOT MATCHED", "page_size": 1}, headers=H).json()["items"][0]
    x = client.get(f"/student/{nl['Roll_No']}/eligible-schemes", headers=H).json()
    assert x["schemes"] == [] and x["summary"] is None
    assert client.get("/student/does-not-exist/eligible-schemes", headers=H).status_code == 404


def test_async_run_and_poll(client, run):
    import time
    r = client.post("/pipeline/run", headers=H)
    assert r.status_code == 200
    rid = r.json()["run_id"]
    for _ in range(120):
        s = client.get(f"/pipeline/runs/{rid}", headers=H).json()
        if s["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.5)
    assert s["status"] == "SUCCEEDED", s.get("error")
    # old results are replaced, not duplicated
    assert client.get("/admin/status", headers=H).json()["counts"]["link_decisions"] == 5000
