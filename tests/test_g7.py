"""Guardrail G7 - top-candidate margin (Record Linkage Rules V3.0)."""
from mosje.linkage import (CandidateScore, JanAadhaarIndex, decide, link_record, normalize_record,
                           weighted_score)
from mosje.matrix import AUTO_LINK, DO_NOT_LINK


def cand(mid, name, father, mother, dob=True, gender=True):
    return CandidateScore(mid, name, name, name, dob, father, mother, gender,
                          weighted_score(name, dob, father, mother, gender))


def test_g7_fail_close_second():
    a = cand("M001", 96, 95, 94)
    b = cand("M002", 94, 92, 91)
    assert (a.overall, b.overall) == (96.80, 95.10)
    d = decide("R1", [a, b])
    assert d.scenario == 1 and d.matrix_action == AUTO_LINK
    assert d.margin == 1.70 and d.g7_status == "FAIL"
    assert d.action == DO_NOT_LINK and d.linked_member_id is None
    assert d.linkage_band == "NOT MATCHED"


def test_g7_pass_clear_winner():
    a = cand("M001", 96, 95, 94)
    b = cand("M002", 94, 65, 65)
    assert b.overall == 84.50
    d = decide("R1", [b, a])
    assert d.margin == 12.30 and d.g7_status == "PASS"
    assert d.action == AUTO_LINK and d.linked_member_id == "M001"


def test_g7_not_applicable_single_candidate():
    d = decide("R1", [cand("M001", 96, 95, 94)])
    assert d.g7_status == "NOT_APPLICABLE" and d.action == AUTO_LINK


def test_g7_boundary_exactly_5_passes():
    a = cand("M001", 100, 100, 100)          # 100.00
    b = cand("M002", 80, 100, 100)           # 95.00
    d = decide("R1", [a, b])
    assert d.margin == 5.0 and d.action == AUTO_LINK


def test_twins_end_to_end():
    ja = [normalize_record("M1", "Priya Sharma", "15-07-2010", "Female", "Rajesh Sharma", "Sunita Sharma"),
          normalize_record("M2", "Piya Sharma", "15-07-2010", "Female", "Rajesh Sharma", "Sunita Sharma")]
    idx = JanAadhaarIndex(ja)
    c = normalize_record("R1", "PRIYA  SARMA", "15/07/2010", "F", "Rajesh Sharma", "Sunita Sharma")
    d = link_record(c, idx)
    assert d.match_method == "FUZZY" and d.candidate_count == 2
    assert d.g7_status == "FAIL" and d.action == DO_NOT_LINK


def test_exact_match_path():
    ja = [normalize_record("M1", "Aarav Sharma", "15-07-2010", "Male", "Rajesh Sharma", "Sunita Sharma")]
    d = link_record(normalize_record("R1", "AARAV  SHARMA", "15 Jul 2010", "M", "RAJESH SHARMA",
                                     "Sunita Sharma."), JanAadhaarIndex(ja))
    assert d.match_method == "EXACT" and d.action == AUTO_LINK and d.overall_score == 100


def test_blocking_dedupes_candidates():
    ja = [normalize_record("M1", "Aarav Sarma", "15-07-2010", "Male", "Rajesh Sharma", "Sunita Sharma")]
    idx = JanAadhaarIndex(ja)
    c = normalize_record("R1", "Aarav Sharma", "15-07-2010", "Male", "Rajesh Sharma", "Sunita Sharma")
    cands = idx.candidates(c)
    assert list(cands) == ["M1"]
    assert set(cands["M1"]) >= {"P1", "P3", "P4"}
    d = link_record(c, idx)
    assert d.overall_score == 98.91 and d.action == AUTO_LINK
