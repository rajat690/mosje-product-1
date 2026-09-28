"""Scheme-rules compiler (Eligibility Rule V3.0, section 7.1).

Turns every row of the scheme master into a structured rule record, once, with a
per-field parse status:
    NO_REQUIREMENT - master says the condition is not specified / open to all -> check PASSES
    PARSED         - a machine-checkable condition was extracted
    UNRESOLVABLE   - the master states a condition exists but it cannot be converted into
                     a computable rule -> check FAILS (no manual verification in V3.0)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Optional

from . import config

NO_REQ, PARSED, UNRES = "NO_REQUIREMENT", "PARSED", "UNRESOLVABLE"

COL_NAME = "Programme / Scheme Name"
COL_LEVEL = "Level"
COL_STATE = "State / UT / Central"
COL_STAGE = "Education Stage (Rule 6)"
COL_AGE = "Age Requirement (from DOB)"
COL_GENDER = "Gender Requirement"
COL_INCOME = "Family Income Requirement"
COL_CATEGORY = "Social Category Requirement (SC/ST/OBC/General/Minority)"
COL_VERIF = "Verification Status"
COL_PORTAL = "Government Application Portal"
COL_DOCS = "Documents Required"
COL_BENEFITS = "Benefits Provided (≤150 chars)"
COL_URL = "Official / Source URL"

STAGES = ("Pre-Matric", "Post-Matric", "Higher Education")
CATEGORIES = ("SC", "ST", "OBC", "General", "Minority")


@dataclass
class SchemeRule:
    Scheme_ID: str
    Master_Row: int
    Scheme_Name: str
    Level_Raw: str
    Scheme_Level: str                      # Central / State/UT
    Scheme_State_UT: str                   # 'Central' or state name
    Education_Stage_Raw: str
    Education_Stage_Allowed: str           # 'Not specified' or '; '-joined set
    Education_Stage_Status: str
    Age_Raw: str
    Age_Min: Optional[int]
    Age_Max: Optional[int]
    Age_Status: str
    Gender_Raw: str
    Gender_Allowed: str                    # 'All' or '; '-joined set
    Gender_Status: str
    Income_Raw: str
    Income_Max: Optional[int]
    Income_Status: str
    Category_Raw: str
    Categories_Allowed: str                # 'All' or '; '-joined set
    Category_Status: str
    Category_Note: str
    Verification_Status: str
    Active_Status: str                     # ACTIVE / EXCLUDED
    Exclusion_Reason: str
    Compile_Status: str                    # COMPLETE / HAS_UNRESOLVABLE / EXCLUDED
    Rule_Version: str
    Effective_From: str
    Effective_To: str
    Application_Portal: str
    Documents_Required: str
    Benefits: str
    Source_URL: str

    # parsed sets (not exported directly)
    stage_set: frozenset = field(default=frozenset(), repr=False)
    gender_set: frozenset = field(default=frozenset(), repr=False)
    category_set: frozenset = field(default=frozenset(), repr=False)

    def export_dict(self):
        d = asdict(self)
        for k in ("stage_set", "gender_set", "category_set"):
            d.pop(k)
        return d


def _s(v) -> str:
    return "" if v is None else str(v).strip()


def _is_not_specified(t: str) -> bool:
    t = t.lower().strip()
    return t == "" or t.startswith("not specified")


# ------------------------------------------------------------------ field parsers
def parse_level(level: str, state: str) -> tuple[str, str]:
    if level.lower().startswith("central"):
        return "Central", "Central"
    return "State/UT", state


def parse_stage(text: str):
    if _is_not_specified(text):
        return "Not specified", frozenset(), NO_REQ
    parts = [p.strip() for p in text.split(";") if p.strip()]
    if parts and all(p in STAGES for p in parts):
        return "; ".join(parts), frozenset(parts), PARSED
    return "", frozenset(), UNRES


_AGE_RANGE = re.compile(r"^(\d{1,2})\s*(?:-|–|to)\s*(\d{1,2})\s*(?:years?|yrs?)?$", re.I)
_AGE_MAX = re.compile(r"^(?:up\s*to|upto|below|under|maximum|max\.?|not\s+more\s+than)\s*(\d{1,2})\s*(?:years?|yrs?)?$", re.I)
_AGE_MIN = re.compile(r"^(?:minimum|min\.?|at\s+least|above)\s*(\d{1,2})\s*(?:years?|yrs?)?$|^(\d{1,2})\s*(?:years?|yrs?)\s*(?:and\s+above|or\s+more|\+)$", re.I)


def parse_age(text: str):
    t = text.strip()
    if _is_not_specified(t) or t.lower() in {"all", "any", "no age limit", "no age bar"}:
        return None, None, NO_REQ
    m = _AGE_RANGE.match(t)
    if m:
        return int(m.group(1)), int(m.group(2)), PARSED
    m = _AGE_MAX.match(t)
    if m:
        v = int(m.group(1))
        return None, (v - 1 if t.lower().startswith(("below", "under")) else v), PARSED
    m = _AGE_MIN.match(t)
    if m:
        v = int(m.group(1) or m.group(2))
        return (v + 1 if t.lower().startswith("above") else v), None, PARSED
    return None, None, UNRES


_GENDER_TOKENS = {"female": "Female", "girls": "Female", "girl": "Female", "women": "Female",
                  "male": "Male", "boys": "Male", "boy": "Male", "men": "Male",
                  "transgender": "Transgender"}


def parse_gender(text: str):
    t = text.strip()
    if _is_not_specified(t) or t.lower() in {"all", "any", "all genders"}:
        return "All", frozenset(), NO_REQ
    parts = [p.strip().lower() for p in re.split(r"[/,;]|\band\b", t) if p.strip()]
    if parts and all(p in _GENDER_TOKENS for p in parts):
        s = frozenset(_GENDER_TOKENS[p] for p in parts)
        return "; ".join(sorted(s)), s, PARSED
    return "", frozenset(), UNRES


_INCOME = re.compile(
    r"^(?:up\s*to|upto|below|less\s+than|not\s+exceeding|maximum|max\.?|≤|<=)?\s*"
    r"(?:₹|rs\.?|inr)?\s*([\d][\d,]*(?:\.\d+)?)\s*(lakh|lakhs|lac|lacs|crore)?\s*"
    r"(?:per\s+annum|p\.?a\.?|per\s+year|/\s*year|annual(?:ly)?)?$", re.I)


def parse_income(text: str):
    t = text.strip()
    tl = t.lower()
    if _is_not_specified(t) or tl in {"no limit", "no income limit", "no income ceiling", "none"}:
        return None, NO_REQ
    m = _INCOME.match(t)
    if m:
        num = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        mult = 100000 if unit.startswith("la") else 10000000 if unit == "crore" else 1
        return int(round(num * mult)), PARSED
    return None, UNRES


_CAT_RE = re.compile(r"\b(SC|ST|OBC|General|Minority|Minorities)\b", re.I)
_CAT_CANON = {"sc": "SC", "st": "ST", "obc": "OBC", "general": "General",
              "minority": "Minority", "minorities": "Minority"}


def parse_category(text: str):
    """Returns (allowed_label, set, status, note)."""
    t = text.strip()
    tl = t.lower()
    if _is_not_specified(t):
        return "All", frozenset(), NO_REQ, "Not specified -> all categories"
    if "all categories" in tl or tl in {"all", "any", "open to all"}:
        note = "Open to all categories"
        rest = [p.strip() for p in t.split(";")[1:] if p.strip()]
        if rest:
            note += f"; extra condition not evaluated in V3.0: {', '.join(rest)}"
        return "All", frozenset(), NO_REQ, note
    if "depending" in tl:
        return "", frozenset(), UNRES, "Category depends on scheme component - cannot be resolved"
    found = frozenset(_CAT_CANON[m.lower()] for m in _CAT_RE.findall(t))
    if not found:
        return "", frozenset(), UNRES, "No supported category (SC/ST/OBC/General/Minority) found"
    pieces = [p.strip() for p in re.split(r"[/,;]", t) if p.strip()]
    ignored = [p for p in pieces if not _CAT_RE.search(p)]
    note = f"Named supported categories only; not mapped: {', '.join(ignored)}" if ignored else ""
    return "; ".join(c for c in CATEGORIES if c in found), found, PARSED, note


# ------------------------------------------------------------------ compiler
def compile_row(row: dict, master_row: int) -> SchemeRule:
    level_raw, state_raw = _s(row.get(COL_LEVEL)), _s(row.get(COL_STATE))
    level, state = parse_level(level_raw, state_raw)
    st_label, st_set, st_status = parse_stage(_s(row.get(COL_STAGE)))
    a_min, a_max, a_status = parse_age(_s(row.get(COL_AGE)))
    g_label, g_set, g_status = parse_gender(_s(row.get(COL_GENDER)))
    i_max, i_status = parse_income(_s(row.get(COL_INCOME)))
    c_label, c_set, c_status, c_note = parse_category(_s(row.get(COL_CATEGORY)))
    verif = _s(row.get(COL_VERIF))
    excluded = "SUPERSEDED / AGGREGATE PLACEHOLDER" in verif.upper()
    statuses = (st_status, a_status, g_status, i_status, c_status)
    compile_status = "EXCLUDED" if excluded else ("HAS_UNRESOLVABLE" if UNRES in statuses else "COMPLETE")
    return SchemeRule(
        Scheme_ID=f"MSM-{master_row:04d}", Master_Row=master_row + 1,  # +1 = Excel row (header is row 1)
        Scheme_Name=_s(row.get(COL_NAME)), Level_Raw=level_raw, Scheme_Level=level,
        Scheme_State_UT=state,
        Education_Stage_Raw=_s(row.get(COL_STAGE)), Education_Stage_Allowed=st_label,
        Education_Stage_Status=st_status,
        Age_Raw=_s(row.get(COL_AGE)), Age_Min=a_min, Age_Max=a_max, Age_Status=a_status,
        Gender_Raw=_s(row.get(COL_GENDER)), Gender_Allowed=g_label, Gender_Status=g_status,
        Income_Raw=_s(row.get(COL_INCOME)), Income_Max=i_max, Income_Status=i_status,
        Category_Raw=_s(row.get(COL_CATEGORY)), Categories_Allowed=c_label,
        Category_Status=c_status, Category_Note=c_note,
        Verification_Status=verif, Active_Status="EXCLUDED" if excluded else "ACTIVE",
        Exclusion_Reason=("Data hygiene: Verification Status marks row as SUPERSEDED / AGGREGATE "
                          "PLACEHOLDER (not a rule change)") if excluded else "",
        Compile_Status=compile_status, Rule_Version=config.RULE_VERSION,
        Effective_From=config.EFFECTIVE_FROM, Effective_To="",
        Application_Portal=_s(row.get(COL_PORTAL)), Documents_Required=_s(row.get(COL_DOCS)),
        Benefits=_s(row.get(COL_BENEFITS)), Source_URL=_s(row.get(COL_URL)),
        stage_set=st_set, gender_set=g_set, category_set=c_set)


def load_master(path=None, sheet=None) -> list[dict]:
    import openpyxl
    wb = openpyxl.load_workbook(path or config.SCHEME_MASTER_PATH, read_only=True, data_only=True)
    ws = wb[sheet or config.SCHEME_MASTER_SHEET]
    rows = ws.iter_rows(values_only=True)
    header = [(_s(h)) for h in next(rows)]
    out = []
    for r in rows:
        if r is None or all(v is None for v in r):
            continue
        out.append(dict(zip(header, r)))
    wb.close()
    return out


def compile_master(path=None) -> list[SchemeRule]:
    return [compile_row(r, i) for i, r in enumerate(load_master(path), start=1)]
