"""Dataset upload: validation, replace-and-run, no-ground-truth metrics, startup does not reseed, restore.

Runs after test_api.py (session fixtures). Replaces the synthetic data with a 500-row sample and restores
the synthetic data at the end of the module.
"""
import gzip
import io
import sys
import time
from pathlib import Path

import pytest
from sqlalchemy import text

from conftest import H

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
from make_upload_sample import make, to_csv  # noqa: E402

CBSE_URL, JA_URL = "/datasets/cbse/upload", "/datasets/jan-aadhaar/upload"
CBSE_HDR = "roll_no,apaar_id,candidate_name,dob,gender,father_name,mother_name,class_passed,school,district,mobile"
JA_HDR = ("jan_aadhaar_id,member_id,nameEng,nameHnd,dob,gender,fatherNameEng,motherNameEng,category,"
          "annual_family_income,district,domicile_state,disability,mobile,relation")


def up(client, url, content: bytes, name="data.csv", **params):
    return client.post(url, headers=H, params=params, files={"file": (name, content, "text/csv")})


@pytest.fixture(scope="module")
def sample():
    return make(500)


@pytest.fixture(scope="module", autouse=True)
def restore_synthetic(client, seeded):
    yield
    r = client.post("/admin/seed", headers=H)
    assert r.status_code == 200 and r.json()["status"] in ("seeded", "skipped"), r.text


def _count(table):
    from db.engine import get_engine
    with get_engine().connect() as c:
        return c.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()


# ------------------------------------------------------------------ validation (nothing changes)
def test_upload_requires_key(client):
    assert client.post(CBSE_URL, files={"file": ("a.csv", b"x", "text/csv")}).status_code == 401
    assert client.post(JA_URL, headers={"X-API-Key": "bad"}, files={"file": ("a.csv", b"x", "text/csv")}).status_code == 401
    assert client.get("/datasets/status").status_code == 401


def test_endpoints_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in (CBSE_URL, JA_URL, "/datasets/status"):
        assert p in paths


def test_status_synthetic_before_upload(client, seeded):
    d = client.get("/datasets/status", headers=H).json()
    assert d["datasets"]["cbse_results"]["source"] == "synthetic" and d["datasets"]["cbse_results"]["rows"] == 5000
    assert d["datasets"]["jan_aadhaar_members"]["rows"] == 21173 and d["ground_truth_available"] is True


def test_missing_and_extra_columns(client, seeded):
    body = b"roll_no,candidate_name,dob,colour\n1,A B,2009-01-01,red\n"
    r = up(client, CBSE_URL, body)
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["ok"] is False
    assert set(d["missing_columns"]) == {"gender", "class_passed", "father_name", "mother_name"}
    assert d["extra_columns"] == ["colour"] and any("missing required column" in e for e in d["errors"])
    assert _count("cbse_results") == 5000                         # nothing changed


def test_bad_rows_sample_capped_at_10(client, seeded):
    rows = [CBSE_HDR]
    for i in range(15):
        rows.append(f"R{i},,Name {i},31-02-2009,Male,F,M,X,S,D,")      # impossible date
    rows.append("R100,,Good,2009-01-01,Robot,F,M,X,S,D,")              # bad gender
    rows.append("R101,,Good,2009-01-01,F,F,M,IX,S,D,")                 # bad class
    rows.append("R0,,Dup,2009-01-01,F,F,M,X,S,D,")                     # duplicate roll_no
    rows.append("R102,,Good,2009-01-01,F,F,M,XII,S,D,")                # fine
    d = up(client, CBSE_URL, "\n".join(rows).encode()).json()["detail"]
    assert d["rows_read"] == 19 and d["bad_row_count"] == 18
    assert len(d["bad_rows_sample"]) == 10 and d["bad_rows_sample"][0]["row"] == 2
    assert "dob '31-02-2009' is not a date" in d["bad_rows_sample"][0]["errors"][0]
    pc = d["problem_counts"]
    assert pc["dob '…' is not a date (use e.g. 2009-04-07, 07-04-2009, 07/04/2009 or 07 Apr 2009)"] == 15
    assert any(k.startswith("gender") for k in pc) and any(k.startswith("class_passed") for k in pc)
    assert any("appears more than once" in k for k in pc)
    assert _count("cbse_results") == 5000


def test_ja_income_and_empty_required(client, seeded):
    body = (JA_HDR + "\nJA1,M1,,,2000-01-01,Male,F,M,SC,abc,D,Rajasthan,No,,Head\n").encode()
    d = up(client, JA_URL, body).json()["detail"]
    errs = d["bad_rows_sample"][0]["errors"]
    assert "nameEng is empty" in errs and any("annual_family_income 'abc'" in e for e in errs)


def test_unreadable_files(client, seeded):
    assert up(client, CBSE_URL, b"").status_code == 422
    r = up(client, CBSE_URL, (CBSE_HDR + "\n").encode())
    assert r.status_code == 422 and "no data rows" in r.json()["detail"]["errors"][0]
    r = up(client, CBSE_URL, b"\xd0\xcf\x11\xe0rest", name="old.xls")
    assert r.status_code == 422 and ".xls" in r.json()["detail"]["errors"][0]


def test_validate_gz_xlsx_and_header_variants():
    from openpyxl import Workbook
    from datetime import datetime
    from db import uploads
    csv_bytes = ("Roll No,Candidate Name,DOB,Gender,Father Name,Mother Name,Class Passed\n"
                 "1,A,07 Apr 2009,F,X,Y,10\n").encode("utf-8-sig")
    rep = uploads.validate(uploads.CBSE, io.BytesIO(gzip.compress(csv_bytes)), "x.csv.gz")
    assert rep.ok and rep.file_format == "csv.gz" and rep.rows_read == 1
    wb = Workbook()
    ws = wb.active
    ws.append(CBSE_HDR.split(","))
    ws.append([12345678, 459224496951, "Test Name", datetime(2009, 4, 7), "Male", "F", "M", "XII", "S", "D", 9999999999])
    buf = io.BytesIO()
    wb.save(buf)
    rep = uploads.validate(uploads.CBSE, buf, "x.xlsx")
    assert rep.ok and rep.file_format == "xlsx", rep.as_dict()
    rows = list(uploads._db_rows(uploads.CBSE, buf, rep, None))
    assert rows[0][0] == "12345678" and rows[0][5] == "2009-04-07" and rows[0][9] == "XII"
    rep = uploads.validate(uploads.CBSE, io.BytesIO("roll_no,candidate_name,dob,gender,father_name,mother_name,"
                                                    "class_passed\n1,Jos\xe9,2009-01-01,M,a,b,X\n".encode("cp1252")),
                           "win.csv")
    assert rep.ok and rep.encoding == "cp1252"


# ------------------------------------------------------------------ replace + run, no ground truth
def test_upload_replaces_and_clears_ground_truth(client, run, sample):
    cbse, ja = sample
    assert client.get("/results/funnel", headers=H).status_code == 200       # synthetic results exist
    r = up(client, CBSE_URL, to_csv(cbse), name="my_cbse.csv")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["rows_loaded"] == 500 and d["source"] == "uploaded" and d["ground_truth_rows_cleared"] == 5000
    assert _count("cbse_results") == 500 and _count("ground_truth") == 0 and _count("link_decisions") == 0
    # old results belonged to the old data
    assert client.get("/results/funnel", headers=H).status_code == 404
    r = up(client, JA_URL, to_csv(ja), name="my_jan_aadhaar.csv")
    assert r.status_code == 200 and r.json()["rows_loaded"] == len(ja)
    st = client.get("/datasets/status", headers=H).json()
    assert st["datasets"]["cbse_results"]["source"] == "uploaded"
    assert st["datasets"]["cbse_results"]["filename"] == "my_cbse.csv" and st["datasets"]["cbse_results"]["rows"] == 500
    assert st["datasets"]["jan_aadhaar_members"]["source"] == "uploaded"
    assert st["datasets"]["ground_truth"]["source"] == "cleared" and st["ground_truth_available"] is False
    assert st["results_ready"] is False and st["datasets"]["cbse_results"]["loaded_at"]


def test_run_on_uploaded_data_without_ground_truth(client, sample):
    r = client.post("/pipeline/run?wait=true", headers=H)
    assert r.status_code == 200 and r.json()["status"] == "SUCCEEDED", r.text
    f = client.get("/results/funnel", headers=H).json()
    fv = {x["Stage"]: x["Count"] for x in f["funnel"]}
    assert fv["CBSE records received"] == 500 and fv["Eligibility-checked (linked students)"] > 300
    assert f["ground_truth"]["available"] is False
    q = f["quality"][0]
    assert q["Segment"] == "OVERALL" and q["Records"] == 500
    assert q["Precision"] is None and q["Recall"] is None and q["True_Matches_TP"] is None
    assert not any(x["Segment"].startswith("Noise:") for x in f["quality"])
    mo = client.get("/results/match-outcomes", headers=H).json()
    assert mo["ground_truth_available"] is False
    assert all(o["Value"] is None and o["Display"] == "not available (no ground truth)" for o in mo["outcomes"])
    assert all(v is None for v in mo["counts"].values())
    sc = client.get("/results/scenarios", headers=H).json()
    assert sc["ground_truth_available"] is False
    t = sc["summary"]["totals"]
    assert t["Records"] == 500 and t["TP"] is None and t["Linked"] == fv["Eligibility-checked (linked students)"]
    assert all(r["TP"] is None and r["FN"] is None for r in sc["rows"])
    s36 = client.get("/results/scenarios-36", headers=H).json()
    assert s36["summary"]["totals"]["Records"] == 500
    assert s36["summary"]["totals"]["True matches (correct link)"] is None
    assert all(r["Missed matches"] is None for r in s36["rows"])
    # views that do not need ground truth keep working
    dec = client.get("/results/decisions", params={"page_size": 5}, headers=H).json()
    assert dec["total"] == 500 and dec["items"][0]["GT_Outcome"] == "n/a"
    assert len(client.get("/results/eligibility-summary", headers=H).json()["rows"]) == fv[
        "Eligibility-checked (linked students)"]
    assert client.get("/outreach/queue", params={"type": "eligible"}, headers=H).json()["total"] > 0
    assert client.get("/results/coverage", headers=H).status_code == 200
    assert client.get("/results/top-schemes", headers=H).json()["rows"]
    roll = client.get("/results/decisions", params={"band": "MATCHED", "page_size": 1}, headers=H).json()[
        "items"][0]["Roll_No"]
    assert client.get(f"/student/{roll}/eligible-schemes", headers=H).json()["schemes"]


def test_upload_with_run_pipeline_flag(client, sample):
    cbse, _ = sample
    r = up(client, CBSE_URL, to_csv(cbse[:200]), name="small.csv", run_pipeline="true")
    assert r.status_code == 200, r.text
    rid = r.json()["pipeline_run_id"]
    for _ in range(240):
        s = client.get(f"/pipeline/runs/{rid}", headers=H).json()
        if s["status"] in ("SUCCEEDED", "FAILED"):
            break
        time.sleep(0.25)
    assert s["status"] == "SUCCEEDED", s.get("error")
    f = client.get("/results/funnel", headers=H).json()
    assert f["counts"]["cbse_records"] == 200 and f["ground_truth"]["available"] is False


def test_partial_ground_truth_is_not_used():
    from api.pipeline_service import ground_truth_coverage
    cbse = [{"roll_no": "1"}, {"roll_no": "2"}]
    assert ground_truth_coverage(cbse, [{"roll_no": "1"}, {"roll_no": "2"}])["available"] is True
    g = ground_truth_coverage(cbse, [{"roll_no": "1"}, {"roll_no": "9"}])
    assert g["available"] is False and "1 of 2" in g["note"]
    assert ground_truth_coverage(cbse, [])["available"] is False


# ------------------------------------------------------------------ restarts must not reseed
def test_startup_does_not_reseed_uploaded_data(client, monkeypatch):
    from api import main
    before = client.get("/datasets/status", headers=H).json()["datasets"]
    monkeypatch.setenv("AUTO_SEED", "true")
    monkeypatch.setenv("AUTO_RUN_PIPELINE", "true")
    main._startup_tasks()                       # what a Render restart runs
    assert main.STATE["startup"] == "ready", main.STATE
    after = client.get("/datasets/status", headers=H).json()["datasets"]
    assert after["cbse_results"]["rows"] == 200 and after["cbse_results"]["source"] == "uploaded"
    assert after["jan_aadhaar_members"]["rows"] == before["jan_aadhaar_members"]["rows"]
    assert after["cbse_results"]["loaded_at"] == before["cbse_results"]["loaded_at"]
    assert _count("ground_truth") == 0


def test_seed_if_empty_seeds_fresh_database(tmp_path):
    from db.engine import make_engine
    from db.seed import seed_if_empty
    eng = make_engine(f"sqlite:///{tmp_path}/fresh.db")
    assert seed_if_empty(eng)["status"] == "seeded"
    r = seed_if_empty(eng)
    assert r["status"] == "skipped" and r["counts"]["cbse_results"] == 5000


def test_admin_seed_restores_synthetic(client):
    r = client.post("/admin/seed", headers=H)          # no force needed: uploaded data is detected
    assert r.status_code == 200 and r.json()["status"] == "seeded", r.text
    st = client.get("/datasets/status", headers=H).json()
    assert st["datasets"]["cbse_results"] == st["datasets"]["cbse_results"] | {"source": "synthetic", "rows": 5000}
    assert st["datasets"]["ground_truth"]["source"] == "synthetic" and st["ground_truth_available"] is True
    assert client.post("/admin/seed", headers=H).json()["status"] == "skipped"     # idempotent again


def test_templates_are_valid_and_match_the_synthetic_headers():
    from db import uploads
    root = Path(__file__).resolve().parent.parent
    for spec, tpl, data in ((uploads.CBSE, "cbse_template.csv", "cbse_passed_2025_26.csv.gz"),
                            (uploads.JAN_AADHAAR, "jan_aadhaar_template.csv", "jan_aadhaar_members.csv.gz")):
        f = root / "templates" / tpl
        rep = uploads.validate(spec, open(f, "rb"), tpl)
        assert rep.ok and rep.rows_read == 3 and not rep.warnings, rep.as_dict()
        header = f.read_text(encoding="utf-8").splitlines()[0].split(",")
        synth = gzip.decompress((root / "data" / data).read_bytes()).decode("utf-8").splitlines()[0].split(",")
        assert header == synth == list(uploads.FILE_ORDER[spec.dataset])
        assert set(header) == set(spec.columns)
        text_ = (root / "templates" / "DATA_DICTIONARY.md").read_text(encoding="utf-8")
        assert all(f"`{c}`" in text_ for c in header)


def test_memory_guard(client, monkeypatch):
    from api import pipeline_service as ps
    assert ps.estimate_memory_mb(5000, 21173) < 450 < ps.estimate_memory_mb(20000, 21173)
    monkeypatch.delenv("PIPELINE_MEMORY_LIMIT_MB", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    assert ps.memory_limit_mb() == 0
    monkeypatch.setenv("RENDER", "true")
    assert ps.memory_limit_mb() == 450
    monkeypatch.setenv("PIPELINE_MEMORY_LIMIT_MB", "50")        # tiny limit: the synthetic data is "too big"
    r = client.post("/pipeline/run", headers=H)
    assert r.status_code == 413 and "MB" in r.json()["detail"]
