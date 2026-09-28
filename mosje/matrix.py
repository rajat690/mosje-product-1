"""56-scenario Record-Linkage Decision Matrix (Record Linkage Rules V3.0, section 3).

Encoded verbatim from the spec. Field bands:
    H   = >=90%          M = 80-89.99%        L = <80%        ANY
Overall bands:
    O90 = >=90   O80 = 80-89.99   O70 = 70-79.99   OLT70 = <70
DOB: EXACT / MISMATCH / ANY.   Gender: EXACT / ANY.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from . import config

AUTO_LINK = "Auto-link"
AUTO_LINK_FLAG = "Auto-link+flag"
DO_NOT_LINK = "Do not link"
DO_NOT_LINK_DISCOVERY = "Do not link + Discovery outreach"

LINK_ACTIONS = {AUTO_LINK, AUTO_LINK_FLAG}


@dataclass(frozen=True)
class Scenario:
    id: int
    overall: str
    name: str
    dob: str
    father: str
    mother: str
    gender: str
    classification: str
    action: str


_ROWS = """
1|O90|H|EXACT|H|H|EXACT|High Confidence|Auto-link
2|O90|H|EXACT|H|M|EXACT|High Confidence|Auto-link
3|O90|H|EXACT|M|H|EXACT|High Confidence|Auto-link
4|O90|H|EXACT|H|L|EXACT|High Confidence with Parent Discrepancy|Auto-link+flag
5|O90|H|EXACT|L|H|EXACT|High Confidence with Parent Discrepancy|Auto-link+flag
6|O90|H|EXACT|M|M|EXACT|High Confidence with Parent Discrepancy|Auto-link+flag
7|O90|H|EXACT|L|L|EXACT|Parent Conflict|Do not link
8|O90|M|EXACT|H|H|EXACT|Candidate Name Discrepancy|Do not link
9|O90|M|EXACT|H|M|EXACT|Multiple Discrepancies|Do not link
10|O90|M|EXACT|M|H|EXACT|Multiple Discrepancies|Do not link
11|O90|M|EXACT|M|M|EXACT|Multiple Discrepancies|Do not link
12|O90|L|EXACT|H|H|EXACT|Candidate Name Conflict|Do not link
13|O90|L|EXACT|H|M|EXACT|Multiple Identity Discrepancies|Do not link
14|O90|L|EXACT|H|L|EXACT|Multiple Identity Discrepancies|Do not link
15|O90|L|EXACT|M|H|EXACT|Multiple Identity Discrepancies|Do not link
16|O90|L|EXACT|L|H|EXACT|Multiple Identity Discrepancies|Do not link
17|O90|L|EXACT|L|L|EXACT|Major Identity Conflict|Do not link
18|O90|H|MISMATCH|H|H|EXACT|DOB Conflict|Do not link
19|O90|H|MISMATCH|H|M|EXACT|DOB Conflict|Do not link
20|O90|H|MISMATCH|M|H|EXACT|DOB Conflict|Do not link
21|O90|M|MISMATCH|H|H|EXACT|Multiple Identity Discrepancies|Do not link
22|O90|L|MISMATCH|M|M|EXACT|Major Identity Conflict|Do not link
23|O90|L|MISMATCH|M|L|EXACT|Major Identity Conflict|Do not link
24|O90|L|MISMATCH|L|M|EXACT|Major Identity Conflict|Do not link
25|O90|L|MISMATCH|L|L|EXACT|Major Identity Conflict|Do not link
26|O90|H|MISMATCH|L|L|EXACT|DOB + Parent Conflict|Do not link
27|O80|H|EXACT|H|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
28|O80|H|EXACT|H|M|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
29|O80|H|EXACT|M|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
30|O80|M|EXACT|H|H|EXACT|Score + Name Below Threshold|Do not link + Discovery outreach
31|O80|M|EXACT|M|M|EXACT|Multiple Threshold Failures|Do not link + Discovery outreach
32|O80|L|EXACT|H|H|EXACT|Candidate Name Conflict|Do not link + Discovery outreach
33|O80|L|EXACT|M|M|EXACT|Major Identity Conflict|Do not link + Discovery outreach
34|O80|L|EXACT|M|L|EXACT|Major Identity Conflict|Do not link + Discovery outreach
35|O80|L|EXACT|L|M|EXACT|Major Identity Conflict|Do not link + Discovery outreach
36|O80|L|EXACT|L|L|EXACT|Major Identity Conflict|Do not link + Discovery outreach
37|O80|ANY|MISMATCH|H|H|EXACT|DOB Conflict|Do not link + Discovery outreach
38|O80|ANY|MISMATCH|M|M|ANY|Multiple Identity Conflicts|Do not link + Discovery outreach
39|O80|ANY|MISMATCH|M|L|ANY|Multiple Identity Conflicts|Do not link + Discovery outreach
40|O80|ANY|MISMATCH|L|M|ANY|Multiple Identity Conflicts|Do not link + Discovery outreach
41|O80|ANY|MISMATCH|L|L|ANY|Multiple Identity Conflicts|Do not link + Discovery outreach
42|O70|H|EXACT|H|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
43|O70|H|EXACT|H|M|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
44|O70|H|EXACT|M|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
45|O70|H|EXACT|M|M|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
46|O70|M|EXACT|H|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
47|O70|M|EXACT|H|M|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
48|O70|M|EXACT|M|H|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
49|O70|M|EXACT|M|M|EXACT|Overall Score Below Threshold|Do not link + Discovery outreach
50|O70|L|EXACT|H|H|EXACT|Score + Name Below Threshold|Do not link + Discovery outreach
51|O70|L|EXACT|M|M|ANY|Multiple Threshold Failures|Do not link + Discovery outreach
52|O70|L|EXACT|M|L|ANY|Multiple Threshold Failures|Do not link + Discovery outreach
53|O70|L|EXACT|L|M|ANY|Multiple Threshold Failures|Do not link + Discovery outreach
54|O70|L|EXACT|L|L|ANY|Multiple Threshold Failures|Do not link + Discovery outreach
55|O70|ANY|MISMATCH|ANY|ANY|ANY|DOB Conflict + Low Score|Do not link + Discovery outreach
56|OLT70|ANY|ANY|ANY|ANY|ANY|No Reliable Match|Do not link
"""

SCENARIOS: list[Scenario] = []
for _line in _ROWS.strip().splitlines():
    _p = _line.split("|")
    SCENARIOS.append(Scenario(int(_p[0]), *_p[1:]))
SCENARIO_BY_ID = {s.id: s for s in SCENARIOS}
assert len(SCENARIOS) == 56


# ------------------------------------------------------------------ banding
def field_band(similarity: float) -> str:
    if similarity >= config.BAND_HIGH:
        return "H"
    if similarity >= config.BAND_MID:
        return "M"
    return "L"


def overall_band(score: float) -> str:
    if score >= config.OVERALL_MATCHED:
        return "O90"
    if score >= 80.0:
        return "O80"
    if score >= config.OVERALL_PROBABLE_LOW:
        return "O70"
    return "OLT70"


BAND_LABEL = {"H": "≥90%", "M": "80–89.99%", "L": "<80%", "ANY": "Any",
              "O90": "≥90", "O80": "80–89.99", "O70": "70–79.99", "OLT70": "<70",
              "EXACT": "Exact", "MISMATCH": "Mismatch"}


@dataclass
class MatrixResult:
    scenario_id: Optional[int]   # None -> default rule (combination not listed)
    classification: str
    action: str


def _m(cell: str, value: str) -> bool:
    return cell == "ANY" or cell == value


def classify(overall: float, name_sim: float, dob_exact: bool, father_sim: float,
             mother_sim: float, gender_exact: bool) -> MatrixResult:
    """Look up the matrix row. Similarities and overall are percentages (2 dp)."""
    ob = overall_band(overall)
    nb, fb, mb = field_band(name_sim), field_band(father_sim), field_band(mother_sim)
    db = "EXACT" if dob_exact else "MISMATCH"
    gb = "EXACT" if gender_exact else "MISMATCH"
    for s in SCENARIOS:
        if (s.overall == ob and _m(s.name, nb) and _m(s.dob, db) and _m(s.father, fb)
                and _m(s.mother, mb) and _m(s.gender, gb)):
            return MatrixResult(s.id, s.classification, s.action)
    # Default rule
    if config.OVERALL_PROBABLE_LOW <= overall < config.OVERALL_MATCHED:
        return MatrixResult(None, "Combination not listed (default rule)", DO_NOT_LINK_DISCOVERY)
    return MatrixResult(None, "Combination not listed (default rule)", DO_NOT_LINK)


# ------------------------------------------------------------------ reachability
_FIELD_RANGE = {"H": (90.0, 100.0), "M": (80.0, 89.99), "L": (0.0, 79.99), "ANY": (0.0, 100.0)}
_OVERALL_RANGE = {"O90": (90.0, 100.0), "O80": (80.0, 89.99), "O70": (70.0, 79.99), "OLT70": (0.0, 69.99)}


def reachable_score_range(s: Scenario) -> tuple[float, float]:
    """Min/max overall score achievable given the row's field conditions."""
    w = config.WEIGHTS
    lo = hi = 0.0
    for key, band in (("name", s.name), ("father", s.father), ("mother", s.mother)):
        a, b = _FIELD_RANGE[band]
        lo += a * w[key] / 100
        hi += b * w[key] / 100
    dob = {"EXACT": (w["dob"], w["dob"]), "MISMATCH": (0.0, 0.0), "ANY": (0.0, w["dob"])}[s.dob]
    gen = {"EXACT": (w["gender"], w["gender"]), "MISMATCH": (0.0, 0.0), "ANY": (0.0, w["gender"])}[s.gender]
    return lo + dob[0] + gen[0], hi + dob[1] + gen[1]


def is_reachable(s: Scenario) -> bool:
    lo, hi = reachable_score_range(s)
    a, b = _OVERALL_RANGE[s.overall]
    return lo <= b and hi >= a
