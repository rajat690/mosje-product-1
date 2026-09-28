"""Eligibility Rule V3.0 examples, Education Stage check and rules-compiler parsing."""
from datetime import date

import pytest

from mosje.eligibility import (ELIGIBLE, FAIL, NOT_ELIGIBLE, NOT_EVAL, PASS, EligibilityEngine,
                               build_profile, check_education_stage, completed_years,
                               derive_education_stage, evaluate_pair)
from mosje.rules_compiler import (NO_REQ, PARSED, UNRES, compile_master, compile_row, parse_category,
                                  parse_income, parse_level)

AS_OF = date(2026, 9, 27)


def scheme(**kw):
    row = {"Programme / Scheme Name": "Test Scheme", "Level": "State", "State / UT / Central": "Rajasthan",
           "Education Stage (Rule 6)": "Post-Matric", "Age Requirement (from DOB)": "Not specified in verified source",
           "Gender Requirement": "All", "Family Income Requirement": "Up to ₹2.5 lakh",
           "Social Category Requirement (SC/ST/OBC/General/Minority)": "SC",
           "Verification Status": "Verified in current research pass"}
    row.update(kw)
    return compile_row(row, 1)


def student(cls="X", **kw):
    m = {"member_id": "M1", "dob": "15-07-2010", "gender": "Male", "annual_family_income": 180000,
         "category": "SC", "domicile_state": "Rajasthan"}
    m.update(kw)
    return build_profile("S1", m, cls, AS_OF)


def test_spec_example_eligible():
    r = evaluate_pair(student(), scheme())
    for col in ("Domicile_Result", "Education_Stage_Result", "Social_Category_Result", "Gender_Result",
                "Income_Result", "Age_Result"):
        assert r[col] == PASS
    assert r["Final_Result"] == ELIGIBLE


def test_spec_failure_example_category():
    r = evaluate_pair(student(), scheme(**{"Social Category Requirement (SC/ST/OBC/General/Minority)": "ST"}),
                      fail_fast=False)
    assert r["Social_Category_Result"] == FAIL
    assert [r[c] for c in ("Domicile_Result", "Age_Result", "Gender_Result", "Income_Result",
                           "Education_Stage_Result")] == [PASS] * 5
    assert r["Final_Result"] == NOT_ELIGIBLE


def test_spec_failure_example_education_stage():
    s = scheme(**{"Education Stage (Rule 6)": "Higher Education"})
    r = evaluate_pair(student("X"), s, fail_fast=False)
    assert r["Education_Stage_Result"] == FAIL and r["Final_Result"] == NOT_ELIGIBLE
    assert evaluate_pair(student("XII"), s)["Final_Result"] == ELIGIBLE


@pytest.mark.parametrize("stage,x_res,xii_res", [
    ("Pre-Matric", FAIL, FAIL), ("Post-Matric", PASS, PASS), ("Higher Education", FAIL, PASS),
    ("Pre-Matric; Post-Matric", PASS, PASS), ("Post-Matric; Higher Education", PASS, PASS),
    ("Not specified", PASS, PASS),
])
def test_education_stage_quick_reference(stage, x_res, xii_res):
    s = scheme(**{"Education Stage (Rule 6)": stage})
    assert check_education_stage(student("X"), s)[0] == x_res
    assert check_education_stage(student("XII"), s)[0] == xii_res


def test_education_stage_derivation():
    assert derive_education_stage("X") == {"Post-Matric"}
    assert derive_education_stage("XII") == {"Post-Matric", "Higher Education"}
    assert derive_education_stage("") is None


def test_class_not_determinable_fails():
    s = scheme(**{"Education Stage (Rule 6)": "Not specified"})
    assert check_education_stage(student(""), s)[0] == FAIL


def test_jurisdiction():
    assert evaluate_pair(student(), scheme(**{"State / UT / Central": "Karnataka"}))["Domicile_Result"] == FAIL
    c = scheme(**{"Level": "Central/CSS", "State / UT / Central": "Central"})
    assert c.Scheme_Level == "Central"
    assert evaluate_pair(student(), c)["Domicile_Result"] == PASS


def test_fail_fast_marks_remaining_not_evaluated():
    r = evaluate_pair(student(), scheme(**{"Education Stage (Rule 6)": "Pre-Matric"}))
    assert r["Education_Stage_Result"] == FAIL
    assert r["Social_Category_Result"] == NOT_EVAL and r["Age_Result"] == NOT_EVAL


def test_not_specified_passes_and_text_income_fails():
    ok = scheme(**{"Family Income Requirement": "Not specified in verified source",
                   "Social Category Requirement (SC/ST/OBC/General/Minority)": "Not specified in verified source",
                   "Gender Requirement": "Not specified in verified source"})
    assert evaluate_pair(student(category="General", annual_family_income=5_000_000), ok)["Final_Result"] == ELIGIBLE
    bad = scheme(**{"Family Income Requirement": "Scheme income ceiling applies"})
    assert bad.Income_Status == UNRES
    assert evaluate_pair(student(), bad)["Income_Result"] == FAIL


def test_income_ceiling_and_missing_income():
    assert evaluate_pair(student(annual_family_income=260000), scheme())["Income_Result"] == FAIL
    assert evaluate_pair(student(annual_family_income=250000), scheme())["Income_Result"] == PASS
    assert evaluate_pair(student(annual_family_income=""), scheme())["Income_Result"] == FAIL


def test_gender_and_unresolvable_age():
    assert evaluate_pair(student(), scheme(**{"Gender Requirement": "Female"}))["Gender_Result"] == FAIL
    r = evaluate_pair(student(), scheme(**{"Age Requirement (from DOB)": "As per scheme rules"}))
    assert r["Age_Result"] == FAIL


def test_age_from_dob():
    assert completed_years("2010-07-15", AS_OF) == 16
    assert completed_years("2010-09-28", AS_OF) == 15
    assert completed_years("2010-09-27", AS_OF) == 16


def test_income_parser():
    assert parse_income("Up to ₹2.5 lakh") == (250000, PARSED)
    assert parse_income("Up to ₹75,000") == (75000, PARSED)
    assert parse_income("Not specified in verified source") == (None, NO_REQ)
    assert parse_income("No limit Std 1-8; up to ₹6 lakh Std 9-10")[1] == UNRES


def test_level_and_category_parsers():
    assert parse_level("Central/Regional", "Central") == ("Central", "Central")
    assert parse_level("State/CSS", "Rajasthan") == ("State/UT", "Rajasthan")
    assert parse_level("UT/CSS", "Ladakh") == ("State/UT", "Ladakh")
    assert parse_category("SC, ST")[1] == {"SC", "ST"}
    assert parse_category("General / all categories")[2] == NO_REQ
    assert parse_category("ST / SC / OBC / General depending scheme")[2] == UNRES


def test_superseded_excluded():
    s = scheme(**{"Verification Status": "SUPERSEDED / AGGREGATE PLACEHOLDER - do not use as scheme row"})
    assert s.Active_Status == "EXCLUDED"
    assert EligibilityEngine([s]).candidate_schemes(student()) == []


def test_real_master_compiles():
    rules = compile_master()
    assert len(rules) == 547
    assert sum(r.Active_Status == "EXCLUDED" for r in rules) == 22
    eng = EligibilityEngine(rules)
    assert all(r.Active_Status == "ACTIVE" for r in eng.rules)


def test_outreach_status():
    eng = EligibilityEngine([scheme()])
    summary, _ = eng.evaluate_student(student(), "t")
    assert summary["Outreach_Status"] == "QUEUE_FOR_OUTREACH" and summary["Rule_Version"] == "V3.0"
    summary, _ = eng.evaluate_student(student(category="ST"), "t")
    assert summary["Outreach_Status"] == "NO_OUTREACH" and summary["Eligible_Scheme_Count"] == 0
