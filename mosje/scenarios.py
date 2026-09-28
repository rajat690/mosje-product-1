"""Scenario-wise outcome table: every row of the 56-row matrix, plus the exact-match path,
"no blocking candidate" and the default rule, with ground-truth outcome counts.

Works on plain decision dicts (the rows written to linkage_decisions.csv / the link_decisions
table) so the same code serves the prototype, the Excel workbook, the dashboard and the API.

Outcome definitions used here (each CBSE record counted exactly once, so TP+FP+FN+TN = Records):
  TP  linked, and linked to the true Jan Aadhaar member
  FP  linked, but to the wrong person (wrong member, or the student is not in Jan Aadhaar at all)
  FN  not linked, but a true match exists in Jan Aadhaar
  TN  not linked, and the student is genuinely not in Jan Aadhaar
Note: this differs from the Match Quality sheet only for wrong-member links, which that sheet
counts both as FP and FN. Here they are FP only, so the four columns add up to the record count.
"""
from __future__ import annotations

from .matrix import (AUTO_LINK, AUTO_LINK_FLAG, BAND_LABEL, DO_NOT_LINK, DO_NOT_LINK_DISCOVERY,
                     SCENARIOS, is_reachable, reachable_score_range)

ACTION_SHORT = {AUTO_LINK: "Auto-link", AUTO_LINK_FLAG: "Auto-link+flag", DO_NOT_LINK: "Do not link",
                DO_NOT_LINK_DISCOVERY: "Do not link + Discovery"}
ACTIONS = ["Auto-link", "Auto-link+flag", "Do not link", "Do not link + Discovery"]
OUTCOMES = ("TP", "FP", "FN", "TN")
UNREACHABLE = "Unreachable"
COUNT_COLS = ("Records", "Linked", "Not_Linked", "TP", "FP", "FN", "TN", "G7_Blocked")


def record_outcome(linked_mid: str | None, true_mid: str | None) -> str:
    linked_mid, true_mid = (linked_mid or "").strip(), (true_mid or "").strip()
    if linked_mid:
        return "TP" if linked_mid == true_mid else "FP"
    return "FN" if true_mid else "TN"


def row_key(dec: dict) -> str:
    """Which table row a decision belongs to."""
    method = dec.get("Match_Method", "")
    if method == "EXACT":
        return "EXACT"
    if method == "NO_CANDIDATE":
        return "NO_CANDIDATE"
    return str(dec.get("Scenario") or "DEFAULT")


def _criteria(s) -> str:
    return (f"Overall {BAND_LABEL[s.overall]} · Name {BAND_LABEL[s.name]} · DOB {BAND_LABEL[s.dob]} · "
            f"Father {BAND_LABEL[s.father]} · Mother {BAND_LABEL[s.mother]} · Gender {BAND_LABEL[s.gender]}")


def table_definition() -> list[dict]:
    """The 59 row definitions (no counts): EXACT, 1..56, NO_CANDIDATE, DEFAULT."""
    rows = [{"Order": 0, "Scenario": "EXACT", "Path": "Exact match (Step 1)",
             "Overall": "100", "Name": "Exact", "DOB": "Exact", "Father": "Exact", "Mother": "Exact",
             "Gender": "Exact",
             "Criteria": "All five fields identical after Level-1 normalisation (unique hit = Scenario 1, "
                         "no fuzzy step; >1 hit = not linked)",
             "Classification": "Exact match", "Action": "Auto-link", "Achievable_Score_Range": "100.00–100.00",
             "Reachability": "Reachable"}]
    for s in SCENARIOS:
        lo, hi = reachable_score_range(s)
        rows.append({"Order": s.id, "Scenario": str(s.id), "Path": "Fuzzy (blocking + weighted score)",
                     "Overall": BAND_LABEL[s.overall], "Name": BAND_LABEL[s.name], "DOB": BAND_LABEL[s.dob],
                     "Father": BAND_LABEL[s.father], "Mother": BAND_LABEL[s.mother],
                     "Gender": BAND_LABEL[s.gender], "Criteria": _criteria(s),
                     "Classification": s.classification, "Action": ACTION_SHORT[s.action],
                     "Achievable_Score_Range": f"{lo:.2f}–{hi:.2f}",
                     "Reachability": "Reachable" if is_reachable(s) else UNREACHABLE})
    rows.append({"Order": 57, "Scenario": "NO_CANDIDATE", "Path": "No blocking candidate",
                 "Overall": "0 (no candidate)", "Name": "-", "DOB": "-", "Father": "-", "Mother": "-",
                 "Gender": "-", "Criteria": "None of the four DOB-based blocking passes returned a Jan Aadhaar "
                                            "candidate; treated as overall 0 → Scenario 56",
                 "Classification": "No Reliable Match", "Action": "Do not link",
                 "Achievable_Score_Range": "0.00–0.00", "Reachability": "Reachable"})
    rows.append({"Order": 58, "Scenario": "DEFAULT", "Path": "Fuzzy – default rule",
                 "Overall": "Any", "Name": "Any", "DOB": "Any", "Father": "Any", "Mother": "Any", "Gender": "Any",
                 "Criteria": "Band combination not listed in the 56 rows (e.g. ≥90 with gender mismatch)",
                 "Classification": "Combination not listed (default rule)",
                 "Action": "Do not link (+ Discovery if 70–89.99)", "Achievable_Score_Range": "0.00–100.00",
                 "Reachability": "Reachable"})
    return rows


def scenario_outcomes(decisions: list[dict]) -> list[dict]:
    """decisions: dicts with Match_Method, Scenario, G7, Linked_Member_ID, GT_True_Member_ID and
    (optionally) Best_Member_ID. Returns one row per table definition with counts."""
    rows = table_definition()
    by_key = {r["Scenario"]: r for r in rows}
    for r in rows:
        r.update({c: 0 for c in COUNT_COLS})
        r["FN_Best_Candidate_Was_True_Member"] = 0
    for d in decisions:
        r = by_key[row_key(d)]
        linked = (d.get("Linked_Member_ID") or "").strip()
        true = (d.get("GT_True_Member_ID") or "").strip()
        o = record_outcome(linked, true)
        r["Records"] += 1
        r["Linked" if linked else "Not_Linked"] += 1
        r[o] += 1
        if d.get("G7") == "FAIL":
            r["G7_Blocked"] += 1
        if o == "FN" and true and (d.get("Best_Member_ID") or "").strip() == true:
            r["FN_Best_Candidate_Was_True_Member"] += 1
    for r in rows:
        if r["Reachability"] == UNREACHABLE:
            assert r["Records"] == 0, f"records landed in unreachable scenario {r['Scenario']}"
            r["Status"] = UNREACHABLE
        else:
            r["Status"] = "Hit" if r["Records"] else "Reachable – 0 records"
        n = r["TP"] + r["FP"]
        r["Precision"] = round(r["TP"] / n, 4) if n else None
    return rows


def totals(rows: list[dict]) -> dict:
    t = {"Scenario": "TOTAL", "Criteria": "All CBSE records", "Status": ""}
    for c in COUNT_COLS + ("FN_Best_Candidate_Was_True_Member",):
        t[c] = sum(r[c] for r in rows)
    return t


def summary(rows: list[dict]) -> dict:
    return {
        "rows": len(rows),
        "matrix_rows": sum(1 for r in rows if r["Scenario"].isdigit()),
        "unreachable": sum(1 for r in rows if r["Status"] == UNREACHABLE),
        "reachable_zero": sum(1 for r in rows if r["Status"].startswith("Reachable")),
        "hit": sum(1 for r in rows if r["Status"] == "Hit"),
        "unreachable_ids": [r["Scenario"] for r in rows if r["Status"] == UNREACHABLE],
        "totals": totals(rows),
    }


def display_rows(rows: list[dict]) -> list[dict]:
    """Copy of rows where count cells of unreachable scenarios read 'Unreachable' (Excel view)."""
    out = []
    for r in rows:
        r = dict(r)
        if r["Status"] == UNREACHABLE:
            for c in COUNT_COLS + ("FN_Best_Candidate_Was_True_Member",):
                r[c] = UNREACHABLE
        out.append(r)
    return out


EXPORT_COLS = ["Scenario", "Path", "Criteria", "Overall", "Name", "DOB", "Father", "Mother", "Gender",
               "Classification", "Action", "Achievable_Score_Range", "Status", "Records", "Linked", "Not_Linked",
               "TP", "FP", "FN", "TN", "G7_Blocked", "FN_Best_Candidate_Was_True_Member", "Precision"]
