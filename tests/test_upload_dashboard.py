"""Dashboard side of uploads: API client upload + error payload, validation display helpers, and the
ground-truth-aware views rendering without crashing when there is no ground truth (Streamlit AppTest)."""
import httpx
import pytest

pytest.importorskip("streamlit")


def test_client_upload_and_422_payload():
    from api_client import ApiError, MosjeApi
    seen = {}

    def handler(req: httpx.Request):
        seen["key"] = req.headers.get("X-API-Key")
        seen["ctype"] = req.headers.get("content-type", "")
        if b"bad" in req.content:
            return httpx.Response(422, json={"detail": {"ok": False, "missing_columns": ["dob"], "errors": ["x"]}})
        return httpx.Response(200, json={"rows_loaded": 3, "filename": "a.csv"})

    api = MosjeApi("http://t", "k", transport=httpx.MockTransport(handler))
    assert api.upload("/datasets/cbse/upload", "a.csv", b"good")["rows_loaded"] == 3
    assert seen["key"] == "k" and seen["ctype"].startswith("multipart/form-data")
    with pytest.raises(ApiError) as e:
        api.upload("/datasets/cbse/upload", "a.csv", b"bad")
    assert e.value.status == 422 and e.value.payload["missing_columns"] == ["dob"]


def test_validation_summary_and_status_frame():
    from upload_view import status_frame, validation_summary
    msgs, table, warns = validation_summary({
        "errors": ["2 row(s) have problems"], "missing_columns": ["gender"], "extra_columns": ["colour"],
        "problem_counts": {"dob '…' is not a date": 2}, "warnings": ["w"],
        "bad_rows_sample": [{"row": 2, "errors": ["dob 'x' is not a date"], "values": {"roll_no": "1"}}]})
    assert "Missing columns: gender" in msgs and "2 × dob '…' is not a date" in msgs and warns == ["w"]
    assert list(table.columns) == ["Line in file", "Problems", "roll_no"] and table.iloc[0]["Line in file"] == 2
    df = status_frame({"datasets": {"cbse_results": {"rows": 500, "source": "uploaded", "filename": "my.csv",
                                                     "loaded_at": "2026-09-28T10:00:00"}}})
    assert df.iloc[0]["Source"] == "Uploaded by you" and df.iloc[0]["Rows now"] == 500


def _views_app():
    import pandas as pd
    import streamlit as st  # noqa: F401
    from match_outcomes_view import render_match_outcomes
    from scenarios36_view import render_scenarios36
    from scenarios_view import render_scenarios
    from mosje.match_outcomes import match_outcomes
    from mosje.scenarios import EXPORT_COLS, scenario_outcomes
    from mosje.scenarios36 import export_rows, scenarios36
    dec = [{"Match_Method": "EXACT", "Scenario": "1", "G7": "PASS", "Linked_Member_ID": "M1",
            "GT_True_Member_ID": "", "Name_Sim_%": 100, "Overall_Score": 100, "DOB": "Exact", "Father_Sim_%": 100,
            "Mother_Sim_%": 100, "Gender": "Match", "Final_Action": "Auto-link", "Margin": 50}]
    rows = scenario_outcomes(dec)
    for r in rows:
        for c in ("TP", "FP", "FN", "TN", "Precision", "FN_Best_Candidate_Was_True_Member"):
            r[c] = None
    render_scenarios(pd.DataFrame([{k: r[k] for k in EXPORT_COLS} for r in rows]), False)
    s36 = export_rows(scenarios36(dec))
    for r in s36:
        for c in ("True matches (correct link)", "False matches (wrong link)", "Missed matches",
                  "Correctly not linked"):
            r[c] = None
    render_scenarios36(s36, False)
    mo = match_outcomes({})
    for o in mo:
        o["Display"] = "not available (no ground truth)"
    render_match_outcomes(mo, {"records": None, "TP": None}, False)


def test_views_render_without_ground_truth():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_views_app, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    vals = [m.value for m in at.metric]
    assert vals.count("n/a") == 12          # scenarios 2 + 36-matrix 4 + match outcomes 6
    assert any("no ground truth" in i.value for i in at.info)


def _upload_app():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path.cwd() / "dashboard"))
    from upload_view import render_upload_section

    class FakeApi:
        def get(self, path, **kw):
            return {"datasets": {"cbse_results": {"rows": 500, "source": "uploaded", "filename": "my.csv"},
                                 "jan_aadhaar_members": {"rows": 21173, "source": "synthetic"},
                                 "ground_truth": {"rows": 0, "source": "cleared"}},
                    "ground_truth_available": False, "results_ready": False}
    render_upload_section(FakeApi())


def test_upload_section_renders():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_function(_upload_app, default_timeout=60)
    at.run()
    assert not at.exception, at.exception
    assert any(b.label.startswith("Run matching") for b in at.button)
    assert len(at.get("file_uploader")) == 2
    assert any("anonymised" in w.value for w in at.warning)
