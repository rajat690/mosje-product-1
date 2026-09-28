"""Scholarship eligibility engine (Scholarship Eligibility Rule V3.0).

Six mandatory AND checks. Bulk execution order and fail-fast per section 7:
    1 Jurisdiction (candidate-set filter) -> 2 Education Stage -> 3 Social Category ->
    4 Gender -> 5 Family Income -> 6 Age
No manual verification: anything that cannot be evaluated is FAIL.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from . import config
from .normalize import l1_dob
from .rules_compiler import NO_REQ, PARSED, UNRES, SchemeRule

PASS, FAIL, NOT_EVAL = "PASS", "FAIL", "NOT_EVALUATED (fail-fast)"
ELIGIBLE, NOT_ELIGIBLE = "ELIGIBLE", "NOT ELIGIBLE"


# ------------------------------------------------------------------ student profile (7.2)
def derive_education_stage(class_passed) -> Optional[frozenset]:
    c = str(class_passed or "").strip().upper().replace("CLASS", "").strip()
    if c in {"X", "10", "10TH"}:
        return frozenset({"Post-Matric"})
    if c in {"XII", "12", "12TH"}:
        return frozenset({"Post-Matric", "Higher Education"})
    return None


def completed_years(dob_iso: Optional[str], as_of: date) -> Optional[int]:
    """Equivalent of Excel DATEDIF(DOB, as_of, "Y")."""
    if not dob_iso:
        return None
    d = datetime.strptime(dob_iso, "%Y-%m-%d").date()
    return as_of.year - d.year - ((as_of.month, as_of.day) < (d.month, d.day))


@dataclass
class StudentProfile:
    Student_ID: str
    Member_ID: str
    Domicile_State_UT: Optional[str]
    DOB: Optional[str]
    Calculated_Age: Optional[int]
    Gender: Optional[str]                 # 'Male' / 'Female' / ...
    Annual_Family_Income: Optional[int]
    Social_Category: Optional[str]
    Student_Education_Stage: Optional[frozenset]
    Class_Passed: str = ""


def build_profile(student_id, member: dict, class_passed, as_of: date = None) -> StudentProfile:
    as_of = as_of or config.ELIGIBILITY_AS_OF_DATE
    dob = l1_dob(member.get("dob"))
    inc = member.get("annual_family_income")
    try:
        inc = int(float(inc)) if inc not in (None, "") else None
    except ValueError:
        inc = None
    g = str(member.get("gender") or "").strip().title() or None
    cat = str(member.get("category") or "").strip() or None
    dom = str(member.get("domicile_state") or "").strip() or None
    return StudentProfile(str(student_id), str(member.get("member_id", "")), dom, dob,
                          completed_years(dob, as_of), g, inc, cat,
                          derive_education_stage(class_passed), str(class_passed or ""))


# ------------------------------------------------------------------ individual checks
def check_jurisdiction(p: StudentProfile, s: SchemeRule):
    if s.Scheme_Level == "Central":
        return PASS, ""
    if p.Domicile_State_UT and p.Domicile_State_UT.lower() == s.Scheme_State_UT.lower():
        return PASS, ""
    return FAIL, f"Jurisdiction: scheme is for {s.Scheme_State_UT}; student domicile {p.Domicile_State_UT or 'unknown'}"


def check_education_stage(p: StudentProfile, s: SchemeRule):
    if p.Student_Education_Stage is None:
        return FAIL, "Education Stage: class passed not determinable from CBSE result"
    if s.Education_Stage_Status == NO_REQ:
        return PASS, ""
    if s.Education_Stage_Status == UNRES:
        return FAIL, f"Education Stage: scheme wording '{s.Education_Stage_Raw}' not a controlled value"
    if p.Student_Education_Stage & s.stage_set:
        return PASS, ""
    return FAIL, (f"Education Stage: student {{{', '.join(sorted(p.Student_Education_Stage))}}} "
                  f"not in scheme {{{s.Education_Stage_Allowed}}}")


def check_category(p: StudentProfile, s: SchemeRule):
    if s.Category_Status == NO_REQ:
        return PASS, ""
    if s.Category_Status == UNRES:
        return FAIL, f"Social Category: scheme wording '{s.Category_Raw}' cannot be resolved"
    if not p.Social_Category:
        return FAIL, "Social Category: student category missing in Jan Aadhaar"
    if p.Social_Category in s.category_set:
        return PASS, ""
    return FAIL, f"Social Category: scheme allows {s.Categories_Allowed}; student is {p.Social_Category}"


def check_gender(p: StudentProfile, s: SchemeRule):
    if s.Gender_Status == NO_REQ:
        return PASS, ""
    if s.Gender_Status == UNRES:
        return FAIL, f"Gender: scheme wording '{s.Gender_Raw}' unclear"
    if not p.Gender:
        return FAIL, "Gender: student gender missing"
    if p.Gender in s.gender_set:
        return PASS, ""
    return FAIL, f"Gender: scheme is for {s.Gender_Allowed}; student is {p.Gender}"


def check_income(p: StudentProfile, s: SchemeRule):
    if s.Income_Status == NO_REQ:
        return PASS, ""
    if s.Income_Status == UNRES:
        return FAIL, f"Family Income: condition stated ('{s.Income_Raw}') but no numeric ceiling"
    if p.Annual_Family_Income is None:
        return FAIL, "Family Income: student family income missing in Jan Aadhaar"
    if p.Annual_Family_Income <= s.Income_Max:
        return PASS, ""
    return FAIL, f"Family Income: ₹{p.Annual_Family_Income:,} > ceiling ₹{s.Income_Max:,}"


def check_age(p: StudentProfile, s: SchemeRule):
    if s.Age_Status == NO_REQ:
        return PASS, ""
    if s.Age_Status == UNRES:
        return FAIL, f"Age: condition '{s.Age_Raw}' cannot be converted to a min/max age"
    if p.Calculated_Age is None:
        return FAIL, "Age: DOB missing/unparseable"
    if s.Age_Min is not None and p.Calculated_Age < s.Age_Min:
        return FAIL, f"Age: {p.Calculated_Age} < minimum {s.Age_Min}"
    if s.Age_Max is not None and p.Calculated_Age > s.Age_Max:
        return FAIL, f"Age: {p.Calculated_Age} > maximum {s.Age_Max}"
    return PASS, ""


# Bulk order (7.9) after the jurisdiction filter
BULK_ORDER = [("Education_Stage_Result", check_education_stage),
              ("Social_Category_Result", check_category),
              ("Gender_Result", check_gender),
              ("Income_Result", check_income),
              ("Age_Result", check_age)]


def evaluate_pair(p: StudentProfile, s: SchemeRule, fail_fast: bool = True) -> dict:
    """Evaluate one student-scheme pair. Returns the 7.12 audit record."""
    out = {"Student_ID": p.Student_ID, "Scheme_ID": s.Scheme_ID, "Scheme_Name": s.Scheme_Name,
           "Scheme_Level": s.Scheme_Level, "Scheme_State_UT": s.Scheme_State_UT}
    res, reason = check_jurisdiction(p, s)
    out["Domicile_Result"] = res
    reasons = [reason] if reason else []
    failed = res == FAIL
    for col, fn in BULK_ORDER:
        if failed and fail_fast:
            out[col] = NOT_EVAL
            continue
        res, reason = fn(p, s)
        out[col] = res
        if res == FAIL:
            failed = True
            reasons.append(reason)
    out["Final_Result"] = NOT_ELIGIBLE if failed else ELIGIBLE
    out["Failure_Reason"] = "; ".join(reasons)
    out["Rule_Version"] = config.RULE_VERSION
    return out


# ------------------------------------------------------------------ bulk engine
class EligibilityEngine:
    def __init__(self, rules: list[SchemeRule], as_of: date = None):
        self.as_of = as_of or config.ELIGIBILITY_AS_OF_DATE
        self.rules = [r for r in rules if r.Active_Status == "ACTIVE"]
        # 7.1 buckets / indexes
        self.CENTRAL_SCHEMES = [r for r in self.rules if r.Scheme_Level == "Central"]
        self.STATE_UT_SCHEMES = defaultdict(list)
        for r in self.rules:
            if r.Scheme_Level != "Central":
                self.STATE_UT_SCHEMES[r.Scheme_State_UT.lower()].append(r)

    def candidate_schemes(self, p: StudentProfile) -> list[SchemeRule]:
        """7.3 Stage 1 jurisdiction filter: Central + student's State/UT."""
        dom = (p.Domicile_State_UT or "").lower()
        return self.CENTRAL_SCHEMES + (self.STATE_UT_SCHEMES.get(dom, []) if dom else [])

    def evaluate_student(self, p: StudentProfile, timestamp: str):
        audits = []
        for s in self.candidate_schemes(p):
            a = evaluate_pair(p, s)
            a["Evaluation_Timestamp"] = timestamp
            audits.append(a)
        elig = [a for a in audits if a["Final_Result"] == ELIGIBLE]
        summary = {
            "Student_ID": p.Student_ID,
            "Member_ID": p.Member_ID,
            "Eligibility_As_Of_Date": self.as_of.isoformat(),
            "Total_Candidate_Schemes_Checked": len(audits),
            "Eligible_Scheme_Count": len(elig),
            "Eligible_Scheme_IDs": "; ".join(a["Scheme_ID"] for a in elig),
            "Eligible_Scheme_Names": "; ".join(a["Scheme_Name"] for a in elig),
            "Not_Eligible_Scheme_Count": len(audits) - len(elig),
            "Rule_Version": config.RULE_VERSION,
            "Outreach_Status": "QUEUE_FOR_OUTREACH" if elig else "NO_OUTREACH",   # 7.13
        }
        return summary, audits
