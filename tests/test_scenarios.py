"""Scenario-wise outcome table (Task A)."""
import csv
from pathlib import Path

from mosje.matrix import SCENARIOS, is_reachable
from mosje.scenarios import (UNREACHABLE, display_rows, record_outcome, row_key, scenario_outcomes, summary,
                             table_definition, totals)

OUT = Path(__file__).resolve().parent.parent / "output"


def dec(method, scen, linked="", true="", g7="NOT_APPLICABLE", best=""):
    return {"Match_Method": method, "Scenario": scen, "Linked_Member_ID": linked, "GT_True_Member_ID": true,
            "G7": g7, "Best_Member_ID": best or linked}


def test_definition_has_all_56_plus_three():
    rows = table_definition()
    assert len(rows) == 59
    assert [r["Scenario"] for r in rows[1:57]] == [str(i) for i in range(1, 57)]
    assert rows[0]["Scenario"] == "EXACT" and rows[57]["Scenario"] == "NO_CANDIDATE" and rows[58]["Scenario"] == "DEFAULT"


def test_record_outcome():
    assert record_outcome("M1", "M1") == "TP"
    assert record_outcome("M1", "M2") == "FP"
    assert record_outcome("M1", "") == "FP"
    assert record_outcome("", "M2") == "FN"
    assert record_outcome("", "") == "TN"


def test_row_key_separates_exact_and_no_candidate():
    assert row_key(dec("EXACT", "1")) == "EXACT"
    assert row_key(dec("FUZZY", "1")) == "1"
    assert row_key(dec("NO_CANDIDATE", "56")) == "NO_CANDIDATE"
    assert row_key(dec("FUZZY", "56")) == "56"
    assert row_key(dec("FUZZY", "DEFAULT")) == "DEFAULT"


def test_counts_and_g7():
    ds = [dec("EXACT", "1", "A", "A"), dec("FUZZY", "1", "B", "B"), dec("FUZZY", "1", "C", "X"),
          dec("FUZZY", "2", "", "D", g7="FAIL", best="D"), dec("FUZZY", "56", "", ""),
          dec("NO_CANDIDATE", "56", "", "E"), dec("FUZZY", "DEFAULT", "", "")]
    rows = {r["Scenario"]: r for r in scenario_outcomes(ds)}
    assert rows["EXACT"]["TP"] == 1 and rows["EXACT"]["Records"] == 1
    assert (rows["1"]["TP"], rows["1"]["FP"]) == (1, 1)
    assert rows["2"]["FN"] == 1 and rows["2"]["G7_Blocked"] == 1 and rows["2"]["FN_Best_Candidate_Was_True_Member"] == 1
    assert rows["56"]["TN"] == 1 and rows["NO_CANDIDATE"]["FN"] == 1 and rows["DEFAULT"]["TN"] == 1
    for r in rows.values():
        assert r["TP"] + r["FP"] + r["FN"] + r["TN"] == r["Records"]
        assert r["Linked"] + r["Not_Linked"] == r["Records"]
    assert totals(list(rows.values()))["Records"] == len(ds)


def test_unreachable_marked_not_zero():
    rows = scenario_outcomes([])
    unreach = {r["Scenario"] for r in rows if r["Status"] == UNREACHABLE}
    assert unreach == {str(s.id) for s in SCENARIOS if not is_reachable(s)}
    assert set(map(str, range(18, 27))) <= unreach
    shown = {r["Scenario"]: r for r in display_rows(rows)}
    assert shown["20"]["Records"] == UNREACHABLE and shown["20"]["TP"] == UNREACHABLE
    assert shown["1"]["Records"] == 0 and shown["1"]["Status"] == "Reachable – 0 records"
    s = summary(rows)
    assert s["matrix_rows"] == 56 and s["unreachable"] == len(unreach)


def test_pipeline_output_reconciles():
    """If the pipeline has been run, the CSV must reconcile with the headline numbers."""
    p = OUT / "scenario_outcomes.csv"
    if not p.exists():
        import pytest
        pytest.skip("run the pipeline first")
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert len(rows) == 59
    n = lambda c: sum(int(r[c]) for r in rows)
    assert n("Records") == 5000
    assert n("TP") + n("FP") == n("Linked")
    dec_rows = list(csv.DictReader(open(OUT / "linkage_decisions.csv", encoding="utf-8")))
    assert n("Linked") == sum(1 for d in dec_rows if d["Linked_Member_ID"])
    assert n("G7_Blocked") == sum(1 for d in dec_rows if d["G7"] == "FAIL")
    for r in rows:
        if r["Status"] == UNREACHABLE:
            assert int(r["Records"]) == 0
