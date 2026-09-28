"""36-Scenario Matrix reporting view (earlier rule engine), classified with V3.0 field scores."""
import csv
from pathlib import Path

import pytest

from mosje.matrix import SCENARIOS, is_reachable
from mosje.scenarios36 import (COUNT_COLS, EXPORT_COLS, NO_CANDIDATE, NOT_LISTED, ORIGINAL_COLUMNS, ROWS36,
                               UNREACHABLE, action36_with_g7, classify36, parse_markdown_rows, row_of, scenarios36,
                               summary, table_definition)

OUT = Path(__file__).resolve().parent.parent / "output"
SOURCE = Path("/home/box/agent-data/agents/740db778-98a1-4428-be1a-8ecadb857058/attachments/"
              "836eeeafaf150df336ec57bc128acb45dba83671d3a96b1fd7a3bdc7c45b43e5.txt")


def dec(overall, name, dob, father, mother, gender, method="FUZZY", linked="", true="", final="Do not link",
        scen="56", g7="NOT_APPLICABLE", margin=None):
    return {"Match_Method": method, "Overall_Score": overall, "Name_Sim_%": name, "DOB": dob, "Father_Sim_%": father,
            "Mother_Sim_%": mother, "Gender": gender, "Linked_Member_ID": linked, "GT_True_Member_ID": true,
            "Final_Action": final, "Scenario": scen, "G7": g7, "Margin": margin}


def test_36_rows_all_original_columns():
    assert len(ROWS36) == 36
    assert ORIGINAL_COLUMNS == ["#", "Overall Score", "Candidate Name", "DOB", "Father Name", "Mother Name", "Gender",
                                "Classification", "Action"]
    assert EXPORT_COLS[:9] == ORIGINAL_COLUMNS
    r13 = ROWS36[12]
    assert (r13["Candidate Name"], r13["Father Name"], r13["Mother Name"]) == ("<80%", "≥90%", "<90%")
    assert ROWS36[31]["Candidate Name"] == "≥80%" and ROWS36[29]["Gender"] == "Any"
    assert [r["Action"] for r in ROWS36[:5]] == ["Auto-link"] * 3 + ["Auto-link+flag"] * 2
    assert all(r["Action"] == "Do not link" for r in ROWS36[5:])


def test_verbatim_against_source_document():
    if not SOURCE.exists():
        pytest.skip("source document not on this machine")
    src = parse_markdown_rows(SOURCE.read_text(encoding="utf-8"))
    assert src == ROWS36


def test_first_matching_row_wins():
    assert classify36(100, 100, "Exact", 100, 100, "Exact") == 1
    assert classify36(95, 95, "Exact", 95, 85, "Exact") == 2
    assert classify36(92, 95, "Exact", 95, 70, "Exact") == 4
    assert classify36(92, 85, "Exact", 95, 95, "Exact") == 8
    assert classify36(75, 95, "Exact", 95, 95, "Exact") == 31      # rows 31 and 32 both hold -> 31
    assert classify36(75, 85, "Exact", 95, 95, "Exact") == 32
    assert classify36(89.99, 95, "Exact", 95, 95, "Exact") == 22     # 80–89.99 upper edge
    assert classify36(90.0, 95, "Exact", 95, 95, "Exact") == 1
    assert classify36(60, 10, "Mismatch", 10, 10, "Mismatch") == 36
    assert classify36(95, 95, "Exact", 95, 95, "Mismatch") is None  # gender mismatch at >=90: not listed


def test_unreachable_rows_under_weights():
    rows = {r["#"]: r for r in table_definition()}
    unreach = {k for k, r in rows.items() if r["Status"] == UNREACHABLE}
    # DOB mismatch caps the score at 70 -> every DOB-mismatch row with overall >= 80 is unreachable
    assert {str(n) for n in range(16, 22)} | {"29", "30"} <= unreach
    assert "35" not in unreach and "36" not in unreach and "1" not in unreach
    # a 36-row mapped only to unreachable V3.0 rows is itself unreachable
    v3_unreach = {str(s.id) for s in SCENARIOS if not is_reachable(s)}
    for k in unreach:
        mapped = set(rows[k]["V3.0 scenario(s) by conditions"].split(", "))
        assert mapped <= v3_unreach | {"DEFAULT", "—"}, k


def test_counts_extra_rows_and_action_notes():
    ds = [dec(100, 100, "Exact", 100, 100, "Exact", method="EXACT", linked="A", true="A", final="Auto-link", scen="1"),
          dec(95, 95, "Exact", 85, 85, "Exact", linked="B", true="B", final="Auto-link+flag", scen="6"),
          dec(95, 95, "Exact", 95, 95, "Exact", true="C", final="Do not link", scen="1", g7="FAIL", margin=1.0),
          dec(0, "", "", "", "", "", method="NO_CANDIDATE", true="D", scen="56"),
          dec(95, 95, "Exact", 95, 95, "Mismatch", scen="DEFAULT"),
          dec(50, 10, "Exact", 10, 10, "Exact", scen="56")]
    assert row_of(ds[3]) == NO_CANDIDATE and row_of(ds[4]) == NOT_LISTED
    rows = {r["Key"]: r for r in scenarios36(ds)}
    r1 = rows["1"]
    assert r1["Records"] == 2 and r1["True matches (correct link)"] == 1 and r1["Missed matches"] == 1
    assert r1["G7-blocked"] == 1 and r1["of which exact path"] == 1
    assert r1["Action differs from V3.0 (records)"] == 0          # G7 applied on both sides
    r6 = rows["6"]
    assert r6["Action differs from V3.0 (records)"] == 1 and "Auto-link+flag" in r6["Note"]
    assert rows[NO_CANDIDATE]["Missed matches"] == 1 and rows[NOT_LISTED]["Correctly not linked"] == 1
    assert rows["36"]["Correctly not linked"] == 1
    for r in rows.values():
        assert sum(r[c] for c in COUNT_COLS[1:5]) == r["Records"]
    s = summary(list(rows.values()))
    assert s["totals"]["Records"] == len(ds) and s["action_differs_records"] == 1


def test_g7_margin_applied_to_link_rows_only():
    assert action36_with_g7("Auto-link", {"Margin": 3}) == "Do not link"
    assert action36_with_g7("Auto-link", {"Margin": 7}) == "Auto-link"
    assert action36_with_g7("Auto-link+flag", {"Margin": None}) == "Auto-link+flag"
    assert action36_with_g7("Do not link", {"Margin": 50}) == "Do not link"


def test_view_helpers():
    pytest.importorskip("streamlit")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scenarios36_view import display_frame, prepare
    from mosje.scenarios36 import export_rows
    df = prepare(export_rows(scenarios36([dec(100, 100, "Exact", 100, 100, "Exact", linked="A", true="A")])))
    assert len(df) == 38 and list(df.columns[:9]) == ORIGINAL_COLUMNS
    shown = display_frame(df)
    assert (shown[df.Status == "Unreachable"]["Records"] == "Unreachable").all()


def test_pipeline_output_reconciles():
    p = OUT / "scenarios36.csv"
    if not p.exists():
        pytest.skip("run the pipeline first")
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert len(rows) == 38 and list(rows[0].keys()) == EXPORT_COLS
    n = lambda c: sum(int(r[c]) for r in rows)  # noqa: E731
    assert n("Records") == 5000
    q = list(csv.DictReader(open(OUT / "match_quality.csv", encoding="utf-8")))[0]
    assert n("True matches (correct link)") == int(q["True_Matches_TP"])
    assert n("Missed matches") == int(q["Missed_Matches_FN"]) and n("False matches (wrong link)") == 0
    dec_rows = list(csv.DictReader(open(OUT / "linkage_decisions.csv", encoding="utf-8")))
    assert n("G7-blocked") == sum(1 for d in dec_rows if d["G7"] == "FAIL")
    assert n("of which exact path") == sum(1 for d in dec_rows if d["Match_Method"] == "EXACT")
    by = {r["#"]: r for r in rows}
    assert int(by["NO_CANDIDATE"]["Records"]) == sum(1 for d in dec_rows if d["Match_Method"] == "NO_CANDIDATE")
    for r in rows:
        if r["Status"] == UNREACHABLE:
            assert int(r["Records"]) == 0
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(OUT / "MoSJE_Prototype_Results.xlsx", read_only=True)
    assert "36-Scenario Matrix" in wb.sheetnames
    sheet = list(wb["36-Scenario Matrix"].iter_rows(values_only=True))
    assert list(sheet[1][:9]) == ORIGINAL_COLUMNS and sheet[-1][0] == "TOTAL" and sheet[-1][10] == 5000
    wb.close()
