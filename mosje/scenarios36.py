"""'36-Scenario Matrix' reporting view (NOT a live rule).

The earlier rule engine's "36 Scenario Record Linkage Decision Matrix" (the table the V3.0 56-row matrix
was expanded from) is kept here verbatim. Each CBSE record's field-level scores, exactly as the V3.0
pipeline computed them for its best candidate (Name_Sim_%, DOB, Father_Sim_%, Mother_Sim_%, Gender,
Overall_Score in linkage_decisions), are classified against the 36 rows: rows are checked top to bottom
and the first row whose every condition holds wins. Counts are ground-truth outcomes of the link V3.0
actually made. V3.0 (mosje.matrix + G7) still decides every link; nothing here changes that.

Extra rows: NO_CANDIDATE (no blocking candidate, so no field scores exist) and NOT_LISTED (scores
exist but no 36-row condition set holds, e.g. gender mismatch at overall >= 70 with a DOB match).
Exact-path records carry field scores of 100 and fall naturally into row 1 (shown separately in
the 'of which exact path' column).
"""
from __future__ import annotations

import itertools
import re

from . import config
from .matrix import SCENARIOS
from .scenarios import record_outcome

# ---- the 36 rows, cell text verbatim from the source document (markdown ** emphasis removed)
ORIGINAL_COLUMNS = ["#", "Overall Score", "Candidate Name", "DOB", "Father Name", "Mother Name", "Gender",
                    "Classification", "Action"]
_SOURCE = """
| 1  |           ≥90 |           ≥90% | Exact        |        ≥90% |        ≥90% | Exact  | **High Confidence**                         | **Auto-link**      |
| 2  |           ≥90 |           ≥90% | Exact        |        ≥90% |   80–89.99% | Exact  | **High Confidence**                         | **Auto-link**      |
| 3  |           ≥90 |           ≥90% | Exact        |   80–89.99% |        ≥90% | Exact  | **High Confidence**                         | **Auto-link**      |
| 4  |           ≥90 |           ≥90% | Exact        |        ≥90% |        <80% | Exact  | **High Confidence with Parent Discrepancy** | **Auto-link+flag** |
| 5  |           ≥90 |           ≥90% | Exact        |        <80% |        ≥90% | Exact  | **High Confidence with Parent Discrepancy** | **Auto-link+flag** |
| 6  |           ≥90 |           ≥90% | Exact        |   80–89.99% |   80–89.99% | Exact  | Probable Match                              | **Do not link**    |
| 7  |           ≥90 |           ≥90% | Exact        |        <80% |        <80% | Exact  | Parent Conflict                             | **Do not link**    |
| 8  |           ≥90 |      80–89.99% | Exact        |        ≥90% |        ≥90% | Exact  | Candidate Name Discrepancy                  | **Do not link**    |
| 9  |           ≥90 |      80–89.99% | Exact        |        ≥90% |   80–89.99% | Exact  | Multiple Discrepancies                      | **Do not link**    |
| 10 |           ≥90 |      80–89.99% | Exact        |   80–89.99% |        ≥90% | Exact  | Multiple Discrepancies                      | **Do not link**    |
| 11 |           ≥90 |      80–89.99% | Exact        |   80–89.99% |   80–89.99% | Exact  | Multiple Discrepancies                      | **Do not link**    |
| 12 |           ≥90 |           <80% | Exact        |        ≥90% |        ≥90% | Exact  | Candidate Name Conflict                     | **Do not link**    |
| 13 |           ≥90 |           <80% | Exact        |        ≥90% |        <90% | Exact  | Multiple Identity Discrepancies             | **Do not link**    |
| 14 |           ≥90 |           <80% | Exact        |        <90% |        ≥90% | Exact  | Multiple Identity Discrepancies             | **Do not link**    |
| 15 |           ≥90 |           <80% | Exact        |        <80% |        <80% | Exact  | Major Identity Conflict                     | **Do not link**    |
| 16 |           ≥90 |           ≥90% | **Mismatch** |        ≥90% |        ≥90% | Exact  | DOB Conflict                                | **Do not link**    |
| 17 |           ≥90 |           ≥90% | **Mismatch** |        ≥90% |   80–89.99% | Exact  | DOB Conflict                                | **Do not link**    |
| 18 |           ≥90 |           ≥90% | **Mismatch** |   80–89.99% |        ≥90% | Exact  | DOB Conflict                                | **Do not link**    |
| 19 |           ≥90 |      80–89.99% | **Mismatch** |        ≥90% |        ≥90% | Exact  | Multiple Identity Discrepancies             | **Do not link**    |
| 20 |           ≥90 |           <80% | **Mismatch** |        <90% |        <90% | Exact  | Major Identity Conflict                     | **Do not link**    |
| 21 |           ≥90 |           ≥90% | **Mismatch** |        <80% |        <80% | Exact  | DOB + Parent Conflict                       | **Do not link**    |
| 22 |      80–89.99 |           ≥90% | Exact        |        ≥90% |        ≥90% | Exact  | Overall Score Below Threshold               | **Do not link**    |
| 23 |      80–89.99 |           ≥90% | Exact        |        ≥90% |   80–89.99% | Exact  | Overall Score Below Threshold               | **Do not link**    |
| 24 |      80–89.99 |           ≥90% | Exact        |   80–89.99% |        ≥90% | Exact  | Overall Score Below Threshold               | **Do not link**    |
| 25 |      80–89.99 |      80–89.99% | Exact        |        ≥90% |        ≥90% | Exact  | Score + Name Below Threshold                | **Do not link**    |
| 26 |      80–89.99 |      80–89.99% | Exact        |   80–89.99% |   80–89.99% | Exact  | Multiple Threshold Failures                 | **Do not link**    |
| 27 |      80–89.99 |           <80% | Exact        |        ≥90% |        ≥90% | Exact  | Candidate Name Conflict                     | **Do not link**    |
| 28 |      80–89.99 |           <80% | Exact        |        <90% |        <90% | Exact  | Major Identity Conflict                     | **Do not link**    |
| 29 |      80–89.99 |            Any | **Mismatch** |        ≥90% |        ≥90% | Exact  | DOB Conflict                                | **Do not link**    |
| 30 |      80–89.99 |            Any | **Mismatch** |        <90% |        <90% | Any    | Multiple Identity Conflicts                 | **Do not link**    |
| 31 |      70–79.99 |           ≥90% | Exact        |        ≥90% |        ≥90% | Exact  | Overall Score Below Threshold               | **Do not link**    |
| 32 |      70–79.99 |           ≥80% | Exact        |        ≥80% |        ≥80% | Exact  | Overall Score Below Threshold               | **Do not link**    |
| 33 |      70–79.99 |           <80% | Exact        |        ≥90% |        ≥90% | Exact  | Score + Name Below Threshold                | **Do not link**    |
| 34 |      70–79.99 |           <80% | Exact        |        <90% |        <90% | Any    | Multiple Threshold Failures                 | **Do not link**    |
| 35 |      70–79.99 |            Any | **Mismatch** |         Any |         Any | Any    | DOB Conflict + Low Score                    | **Do not link**    |
| 36 |           <70 |            Any | Any          |         Any |         Any | Any    | No Reliable Match                           | **Do not link**    |
"""


def parse_markdown_rows(text: str) -> list[dict]:
    """Parse '| 1 | ≥90 | ... |' lines into dicts keyed by ORIGINAL_COLUMNS (emphasis markers stripped)."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip().replace("**", "") for c in line.strip().strip("|").split("|")]
        if len(cells) == len(ORIGINAL_COLUMNS) and cells[0].isdigit():
            rows.append(dict(zip(ORIGINAL_COLUMNS, cells)))
    return rows


ROWS36 = parse_markdown_rows(_SOURCE)
assert len(ROWS36) == 36 and [int(r["#"]) for r in ROWS36] == list(range(1, 37))

LINK_ACTIONS36 = {"Auto-link", "Auto-link+flag"}
NO_CANDIDATE, NOT_LISTED, UNREACHABLE = "NO_CANDIDATE", "NOT_LISTED", "Unreachable"
COUNT_COLS = ["Records", "True matches (correct link)", "False matches (wrong link)", "Missed matches",
              "Correctly not linked", "G7-blocked"]
OUTCOME_COL = {"TP": "True matches (correct link)", "FP": "False matches (wrong link)", "FN": "Missed matches",
               "TN": "Correctly not linked"}


# ---- condition parsing: a cell becomes a numeric interval [lo, hi) (or a categorical set)
def _interval(cell: str) -> tuple[float, float]:
    c = cell.replace("%", "").strip()
    if c == "Any":
        return (float("-inf"), float("inf"))
    if m := re.fullmatch(r"≥\s*([\d.]+)", c):
        return (float(m[1]), float("inf"))
    if m := re.fullmatch(r"<\s*([\d.]+)", c):
        return (float("-inf"), float(m[1]))
    if m := re.fullmatch(r"([\d.]+)\s*[–-]\s*([\d.]+)", c):   # '80–89.99' = 80 <= x < 90 (2-dp scores)
        return (float(m[1]), round(float(m[2]) + 0.01, 2))
    raise ValueError(f"cannot parse band {cell!r}")


def _cat(cell: str) -> set[str]:
    return {"Exact", "Mismatch"} if cell == "Any" else {cell}


def _in(v: float, iv: tuple[float, float]) -> bool:
    return iv[0] <= v < iv[1]


COND = [{"n": int(r["#"]), "overall": _interval(r["Overall Score"]), "name": _interval(r["Candidate Name"]),
         "dob": _cat(r["DOB"]), "father": _interval(r["Father Name"]), "mother": _interval(r["Mother Name"]),
         "gender": _cat(r["Gender"])} for r in ROWS36]


def classify36(overall: float, name: float, dob: str, father: float, mother: float, gender: str) -> int | None:
    """First 36-row whose conditions all hold (top to bottom), else None (= NOT_LISTED)."""
    for c in COND:
        if (_in(overall, c["overall"]) and _in(name, c["name"]) and dob in c["dob"] and _in(father, c["father"])
                and _in(mother, c["mother"]) and gender in c["gender"]):
            return c["n"]
    return None


# ---- reachability (weights 30/25/20/20/5) and the static 36 -> V3.0 row mapping, by band enumeration.
# Every 36-row field condition is a union of the bands L (<80), M (80-89.99), H (>=90), so enumerating
# band combinations is exact.
_FB = {"L": (0.0, 79.99), "M": (80.0, 89.99), "H": (90.0, 100.0)}
_OB = {"O90": (90.0, 100.0), "O80": (80.0, 89.99), "O70": (70.0, 79.99), "OLT70": (0.0, 69.99)}
_FB_IV = {"L": (0.0, 80.0), "M": (80.0, 90.0), "H": (90.0, 100.01)}
_OB_IV = {"O90": (90.0, 100.01), "O80": (80.0, 90.0), "O70": (70.0, 80.0), "OLT70": (0.0, 70.0)}


def _covers(iv, band_iv) -> bool:
    return iv[0] <= band_iv[0] and band_iv[1] <= iv[1]


def _combo_rows36(ob, nb, db, fb, mb, gb) -> list[int]:
    return [c["n"] for c in COND if _covers(c["overall"], _OB_IV[ob]) and _covers(c["name"], _FB_IV[nb])
            and db in c["dob"] and _covers(c["father"], _FB_IV[fb]) and _covers(c["mother"], _FB_IV[mb])
            and gb in c["gender"]]


def _combo_reachable(ob, nb, db, fb, mb, gb) -> bool:
    w = config.WEIGHTS
    lo = sum(_FB[b][0] * w[k] / 100 for k, b in (("name", nb), ("father", fb), ("mother", mb)))
    hi = sum(_FB[b][1] * w[k] / 100 for k, b in (("name", nb), ("father", fb), ("mother", mb)))
    extra = (w["dob"] if db == "Exact" else 0) + (w["gender"] if gb == "Exact" else 0)
    a, b = _OB[ob]
    return lo + extra <= b and hi + extra >= a


_V3_BAND = {"Exact": "EXACT", "Mismatch": "MISMATCH"}


def _v3_rows(ob, nb, db, fb, mb, gb) -> str:
    for s in SCENARIOS:
        if (s.overall == ob and s.name in ("ANY", nb) and s.dob in ("ANY", _V3_BAND[db]) and s.father in ("ANY", fb)
                and s.mother in ("ANY", mb) and s.gender in ("ANY", _V3_BAND[gb])):
            return str(s.id)
    return "DEFAULT"


def row_analysis() -> dict[int, dict]:
    """Per 36-row: reachable in isolation, wins any reachable combination (first match), V3.0 rows it maps to."""
    out = {c["n"]: {"reachable": False, "wins": False, "v3": set(), "v3_reachable": set()} for c in COND}
    for combo in itertools.product(_OB, _FB, ("Exact", "Mismatch"), _FB, _FB, ("Exact", "Mismatch")):
        hits = _combo_rows36(*combo)
        reach = _combo_reachable(*combo)
        v3 = _v3_rows(*combo)
        for n in hits:
            out[n]["v3"].add(v3)
            if reach:
                out[n]["reachable"] = True
        if hits:
            first = out[hits[0]]
            if reach:
                first["wins"] = True
                first["v3_reachable"].add(v3)
    return out


def _sort_v3(ids) -> str:
    return ", ".join(sorted(ids, key=lambda x: (not x.isdigit(), int(x) if x.isdigit() else 0, x))) or "—"


def table_definition() -> list[dict]:
    an = row_analysis()
    rows = []
    for r in ROWS36:
        a = an[int(r["#"])]
        status = ("Reachable" if a["wins"] else "Shadowed (an earlier row always matches first)") \
            if a["reachable"] else UNREACHABLE
        rows.append({"Key": r["#"], **r, "Status": status,
                     "V3.0 scenario(s) by conditions": _sort_v3(a["v3_reachable"] if a["wins"] else a["v3"])})
    blank = {c: "" for c in ORIGINAL_COLUMNS}
    rows.append({"Key": NO_CANDIDATE, **blank, "#": "NO_CANDIDATE", "Overall Score": "0 (no candidate)",
                 "Classification": "No blocking candidate (no field scores; conceptually row 36)",
                 "Action": "Do not link", "Status": "Reachable", "V3.0 scenario(s) by conditions": "56"})
    rows.append({"Key": NOT_LISTED, **blank, "#": "NOT_LISTED", "Overall Score": "Any",
                 "Classification": "Scores match none of the 36 rows (e.g. gender mismatch, overall ≥70)",
                 "Action": "(none – not in the 36-row matrix)", "Status": "Reachable",
                 "V3.0 scenario(s) by conditions": "—"})
    return rows


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def row_of(d: dict) -> str:
    if d.get("Match_Method") == "NO_CANDIDATE" or _num(d.get("Name_Sim_%")) is None:
        return NO_CANDIDATE
    n = classify36(_num(d.get("Overall_Score")), _num(d.get("Name_Sim_%")), d.get("DOB") or "",
                   _num(d.get("Father_Sim_%")), _num(d.get("Mother_Sim_%")), d.get("Gender") or "")
    return str(n) if n else NOT_LISTED


def _link_class(action: str) -> str:
    return action if action in LINK_ACTIONS36 else "Do not link"


def action36_with_g7(action36: str, d: dict) -> str:
    """36-row action with the doc's top-candidate margin rule (the V3.0 G7 margin) applied to link rows."""
    if action36 in LINK_ACTIONS36:
        m = _num(d.get("Margin"))
        if m is not None and m < config.G7_MIN_MARGIN:
            return "Do not link"
    return _link_class(action36)


def scenarios36(decisions: list[dict]) -> list[dict]:
    rows = table_definition()
    by = {r["Key"]: r for r in rows}
    obs, diff, exact = ({k: {} for k in by} for _ in range(3))
    for r in rows:
        r.update({c: 0 for c in COUNT_COLS})
    for d in decisions:
        key = row_of(d)
        r = by[key]
        o = record_outcome(d.get("Linked_Member_ID"), d.get("GT_True_Member_ID"))
        r["Records"] += 1
        r[OUTCOME_COL[o]] += 1
        if d.get("G7") == "FAIL":
            r["G7-blocked"] += 1
        v3 = "EXACT path (1)" if d.get("Match_Method") == "EXACT" else str(d.get("Scenario") or "DEFAULT")
        obs[key][v3] = obs[key].get(v3, 0) + 1
        if d.get("Match_Method") == "EXACT":
            exact[key]["n"] = exact[key].get("n", 0) + 1
        if key != NOT_LISTED:
            want = action36_with_g7(r["Action"], d)
            got = _link_class(d.get("Final_Action") or "")
            if want != got:
                k2 = (want, d.get("Final_Action"), v3)
                diff[key][k2] = diff[key].get(k2, 0) + 1
    for r in rows:
        k = r["Key"]
        if r["Status"] == UNREACHABLE:
            assert r["Records"] == 0, f"records landed in unreachable 36-row {k}"
        r["of which exact path"] = exact[k].get("n", 0)
        r["V3.0 scenario(s) observed"] = "; ".join(
            f"{s} ×{n}" for s, n in sorted(obs[k].items(), key=lambda x: -x[1])) or "—"
        nd = sum(diff[k].values())
        r["Action differs from V3.0 (records)"] = nd
        r["Note"] = "; ".join(f"{n} record(s): 36-row → {w}, V3.0 gave {g} (V3.0 row {s})"
                              for (w, g, s), n in sorted(diff[k].items(), key=lambda x: -x[1])) if nd else ""
        if k == NOT_LISTED and r["Records"]:
            r["Note"] = "No 36-row action applies; V3.0 gave: " + "; ".join(
                f"{s} ×{n}" for s, n in sorted(obs[k].items(), key=lambda x: -x[1]))
    return rows


EXPORT_COLS = ORIGINAL_COLUMNS + ["Status"] + COUNT_COLS + ["of which exact path", "V3.0 scenario(s) by conditions",
                                                         "V3.0 scenario(s) observed",
                                                         "Action differs from V3.0 (records)", "Note"]


def export_rows(rows: list[dict]) -> list[dict]:
    return [{c: r[c] for c in EXPORT_COLS} for r in rows]


def display_rows(rows: list[dict]) -> list[dict]:
    """Excel/dashboard view: count cells of unreachable rows read 'Unreachable'."""
    out = []
    for r in rows:
        r = dict(r)
        if r["Status"] == UNREACHABLE:
            for c in COUNT_COLS + ["of which exact path"]:
                r[c] = UNREACHABLE
        out.append(r)
    return out


def summary(rows: list[dict]) -> dict:
    t = {c: sum(r[c] for r in rows) for c in COUNT_COLS}
    return {"rows": len(rows), "matrix_rows": 36,
            "unreachable_ids": [r["#"] for r in rows if r["Status"] == UNREACHABLE],
            "shadowed_ids": [r["#"] for r in rows if r["Status"].startswith("Shadowed")],
            "hit_ids": [r["#"] for r in rows if r["Records"]],
            "action_differs_records": sum(r["Action differs from V3.0 (records)"] for r in rows),
            "not_listed_records": next(r["Records"] for r in rows if r["Key"] == NOT_LISTED),
            "totals": t}
