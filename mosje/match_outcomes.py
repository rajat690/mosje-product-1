"""'Match Outcomes': the six headline linkage outcomes against ground truth, in plain English.

Pure presentation of numbers that mosje.metrics.summarize() already computes (Record Linkage Rules
V3.0, section 8). Nothing here changes a linkage or eligibility rule. Used by the prototype
(Excel sheet + dashboard tab) and by the platform API (GET /results/match-outcomes).
"""
from __future__ import annotations

# (key, label, source column in the match-quality row, kind, formula, plain-English definition, better)
OUTCOMES = [
    ("true_matches", "True matches found", "True_Matches_TP", "count", "TP",
     "Students we linked to their correct Jan Aadhaar record.", "Higher"),
    ("false_matches", "False matches", "False_Matches_FP", "count", "FP",
     "Links we made that are wrong: the student was linked to the wrong person, or linked although "
     "they are not in Jan Aadhaar at all.", "Lower"),
    ("missed_matches", "Missed matches", "Missed_Matches_FN", "count", "FN",
     "Students who are in Jan Aadhaar but whom we did not link to their record.", "Lower"),
    ("precision", "Precision", "Precision", "ratio", "TP / (TP + FP)",
     "Correct links / all links made. Of every link we made, the share that is right.", "Higher"),
    ("recall", "Recall", "Recall", "ratio", "TP / (TP + FN)",
     "Correct links / all students who could have been linked. Of the students who really are in Jan "
     "Aadhaar, the share we found.", "Higher"),
    ("false_positive_rate", "False-positive rate", "False_Positive_Rate", "ratio", "FP / (FP + TN)",
     "Wrong links / students not in Jan Aadhaar. Of the students who should NOT be linked, the share we "
     "linked anyway.", "Lower"),
]
COLUMNS = ["Outcome", "Value", "Display", "Formula", "Definition", "Better_When"]


def _display(value, kind: str) -> str:
    if value is None or value == "":
        return "n/a"
    return f"{int(value):,}" if kind == "count" else f"{float(value):.3f}"


def match_outcomes(quality_row: dict) -> list[dict]:
    """Six outcome rows (fixed order) from the OVERALL row of the match-quality table."""
    out = []
    for key, label, col, kind, formula, definition, better in OUTCOMES:
        v = quality_row.get(col)
        if v is not None and v != "":
            v = int(float(v)) if kind == "count" else round(float(v), 4)
        else:
            v = None
        out.append({"Key": key, "Outcome": label, "Value": v, "Display": _display(v, kind), "Formula": formula,
                    "Definition": definition, "Better_When": better})
    return out


def overall_row(quality: list[dict]) -> dict:
    for r in quality:
        if r.get("Segment") == "OVERALL":
            return r
    return quality[0] if quality else {}


def payload(quality: list[dict]) -> dict:
    """Outcomes plus the underlying counts (TN / records) so readers can check the arithmetic."""
    ov = overall_row(quality)
    num = lambda c: int(float(ov[c])) if ov.get(c) not in (None, "") else None  # noqa: E731
    return {"outcomes": match_outcomes(ov),
            "counts": {"records": num("Records"), "records_with_true_ja_member": num("Records_with_true_JA_member"),
                       "TP": num("True_Matches_TP"), "FP": num("False_Matches_FP"),
                       "FN": num("Missed_Matches_FN"), "TN": num("True_Negatives_TN")}}
