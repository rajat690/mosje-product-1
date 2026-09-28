"""Match Outcomes: six headline outcomes with plain-English definitions (presentation only)."""
import csv
from pathlib import Path

import pytest

from mosje.match_outcomes import OUTCOMES, match_outcomes, overall_row, payload
from mosje.metrics import outcome, summarize

OUT = Path(__file__).resolve().parent.parent / "output"
LABELS = ["True matches found", "False matches", "Missed matches", "Precision", "Recall", "False-positive rate"]


def _rows(pairs):
    rows = []
    for linked, true in pairs:
        o = outcome(linked, true)
        rows.append({**o, "probable": False, "true_mid": true})
    return rows


def test_exactly_six_outcomes_in_order_with_definitions():
    rows = match_outcomes(summarize(_rows([("A", "A")]), "OVERALL"))
    assert [r["Outcome"] for r in rows] == LABELS
    assert all(r["Definition"] and r["Formula"] for r in rows)
    prec = rows[3]
    assert "correct links / all links" in prec["Definition"].lower() and prec["Formula"] == "TP / (TP + FP)"
    assert len(OUTCOMES) == 6


def test_values_follow_metrics_summarize():
    # 3 TP, 1 wrong member (FP+FN), 1 missed (FN), 1 linked-but-not-in-JA (FP), 2 TN
    pairs = [("A", "A"), ("B", "B"), ("C", "C"), ("X", "D"), ("", "E"), ("Y", ""), ("", ""), ("", "")]
    s = summarize(_rows(pairs), "OVERALL")
    v = {r["Key"]: r["Value"] for r in match_outcomes(s)}
    assert (v["true_matches"], v["false_matches"], v["missed_matches"]) == (3, 2, 2)
    assert v["precision"] == round(3 / 5, 4) and v["recall"] == round(3 / 5, 4)
    assert v["false_positive_rate"] == round(2 / (2 + 2), 4)   # FP / (FP + TN), as in metrics.py


def test_undefined_ratios_show_na():
    s = summarize(_rows([("", "")]), "OVERALL")      # no links, nobody in JA
    d = {r["Key"]: r for r in match_outcomes(s)}
    assert d["precision"]["Value"] is None and d["precision"]["Display"] == "n/a"
    assert d["recall"]["Display"] == "n/a" and d["false_positive_rate"]["Display"] == "0.000"


def test_display_formatting_and_overall_row():
    q = [{"Segment": "Class X", "True_Matches_TP": 1}, {"Segment": "OVERALL", "Records": 5000,
         "Records_with_true_JA_member": 4250, "True_Matches_TP": 3712, "False_Matches_FP": 0,
         "Missed_Matches_FN": 538, "True_Negatives_TN": 750, "Precision": 1.0, "Recall": 0.8734,
         "False_Positive_Rate": 0.0}]
    assert overall_row(q)["Segment"] == "OVERALL"
    p = payload(q)
    assert [r["Display"] for r in p["outcomes"]] == ["3,712", "0", "538", "1.000", "0.873", "0.000"]
    assert p["counts"] == {"records": 5000, "records_with_true_ja_member": 4250, "TP": 3712, "FP": 0, "FN": 538,
                           "TN": 750}


def test_view_helpers_order_and_table():
    pytest.importorskip("streamlit")
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import pandas as pd
    from match_outcomes_view import ORDER, explanatory_table, outcomes_frame
    rows = match_outcomes(summarize(_rows([("A", "A"), ("", "B")]), "OVERALL"))
    df = outcomes_frame(list(reversed(rows)))
    assert list(df.Key) == ORDER
    t = explanatory_table(df)
    assert list(t.columns) == ["Outcome", "Result", "How it is calculated", "What it means", "Better when"]
    assert len(t) == 6
    with pytest.raises(ValueError):
        outcomes_frame(pd.DataFrame(rows[:5]))


def test_pipeline_output_has_match_outcomes():
    """If the pipeline has been run: CSV + Excel sheet reconcile with match_quality.csv."""
    p = OUT / "match_outcomes.csv"
    if not p.exists():
        pytest.skip("run the pipeline first")
    rows = list(csv.DictReader(open(p, encoding="utf-8")))
    assert [r["Outcome"] for r in rows] == LABELS
    q = list(csv.DictReader(open(OUT / "match_quality.csv", encoding="utf-8")))
    ov = overall_row(q)
    v = {r["Key"]: r["Value"] for r in rows}
    assert int(v["true_matches"]) == int(ov["True_Matches_TP"])
    assert int(v["false_matches"]) == int(ov["False_Matches_FP"])
    assert int(v["missed_matches"]) == int(ov["Missed_Matches_FN"])
    assert float(v["precision"]) == float(ov["Precision"]) and float(v["recall"]) == float(ov["Recall"])
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.load_workbook(OUT / "MoSJE_Prototype_Results.xlsx", read_only=True)
    assert "Match Outcomes" in wb.sheetnames
    sheet = list(wb["Match Outcomes"].iter_rows(values_only=True))
    assert [r[0] for r in sheet[2:8]] == LABELS
    wb.close()
