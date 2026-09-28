"""Repository layer: every SQL query the API uses lives here (inputs, results, reference data)."""
from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from mosje.normalize import l1_dob, l1_gender


def _s(v) -> str:
    return "" if v is None else str(v)


# ------------------------------------------------------------------ inputs -> engine-shaped dicts
def load_ja_for_engine(conn: Connection) -> list[dict]:
    """Jan Aadhaar members with the original CSV column names (what mosje.pipeline.compute expects)."""
    rows = conn.execute(text(
        "SELECT jan_aadhaar_id, member_id, name_eng, name_hnd, dob_raw, gender, father_name_eng, mother_name_eng, "
        "category, annual_family_income, district, domicile_state, disability, mobile, relation "
        "FROM jan_aadhaar_members ORDER BY member_id")).mappings()
    return [{"jan_aadhaar_id": _s(r["jan_aadhaar_id"]), "member_id": _s(r["member_id"]), "nameEng": _s(r["name_eng"]),
             "nameHnd": _s(r["name_hnd"]), "dob": _s(r["dob_raw"]), "gender": _s(r["gender"]),
             "fatherNameEng": _s(r["father_name_eng"]), "motherNameEng": _s(r["mother_name_eng"]),
             "category": _s(r["category"]), "annual_family_income": _s(r["annual_family_income"]),
             "district": _s(r["district"]), "domicile_state": _s(r["domicile_state"]),
             "disability": _s(r["disability"]), "mobile": _s(r["mobile"]), "relation": _s(r["relation"])}
            for r in rows]




def load_cbse_for_engine(conn: Connection) -> list[dict]:
    rows = conn.execute(text(
        "SELECT roll_no, apaar_id, candidate_name, dob_raw, gender, father_name, mother_name, class_passed, school, "
        "district, mobile FROM cbse_results ORDER BY roll_no")).mappings()
    return [{"roll_no": _s(r["roll_no"]), "apaar_id": _s(r["apaar_id"]), "candidate_name": _s(r["candidate_name"]),
             "dob": _s(r["dob_raw"]), "gender": _s(r["gender"]), "father_name": _s(r["father_name"]),
             "mother_name": _s(r["mother_name"]), "class_passed": _s(r["class_passed"]), "school": _s(r["school"]),
             "district": _s(r["district"]), "mobile": _s(r["mobile"])} for r in rows]


def load_truth_for_engine(conn: Connection) -> list[dict]:
    rows = conn.execute(text("SELECT * FROM ground_truth ORDER BY roll_no")).mappings()
    return [{k: _s(v) for k, v in r.items()} for r in rows]


def load_master_rows(conn: Connection) -> list[dict]:
    return [json.loads(r[0]) for r in
            conn.execute(text("SELECT raw_json FROM scheme_master ORDER BY master_row"))]


# ------------------------------------------------------------------ status
def counts(conn: Connection) -> dict:
    out = {}
    for t in ("jan_aadhaar_members", "cbse_results", "ground_truth", "scheme_master", "scheme_rules",
              "link_decisions", "eligibility_results", "outreach_queue", "pipeline_runs"):
        out[t] = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
    return out


def latest_run(conn: Connection, succeeded_only: bool = True) -> Optional[dict]:
    q = "SELECT * FROM pipeline_runs "
    if succeeded_only:
        q += "WHERE status = 'SUCCEEDED' "
    q += "ORDER BY started_at DESC LIMIT 1"
    r = conn.execute(text(q)).mappings().first()
    return _run(r) if r else None


def get_run(conn: Connection, run_id: str) -> Optional[dict]:
    r = conn.execute(text("SELECT * FROM pipeline_runs WHERE run_id = :r"), {"r": run_id}).mappings().first()
    return _run(r) if r else None


def list_runs(conn: Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(text("SELECT run_id, status, started_at, finished_at, triggered_by, error FROM pipeline_runs "
                             "ORDER BY started_at DESC LIMIT :n"), {"n": limit}).mappings()
    return [dict(r) for r in rows]


def _run(r) -> dict:
    d = dict(r)
    d["results"] = json.loads(d.pop("results_json") or "{}")
    return d


# ------------------------------------------------------------------ paging helper
def page(conn: Connection, base_sql: str, params: dict, order: str, page_no: int, page_size: int):
    total = conn.execute(text(f"SELECT COUNT(*) FROM ({base_sql}) AS q"), params).scalar()
    rows = conn.execute(text(f"{base_sql} ORDER BY {order} LIMIT :_lim OFFSET :_off"),
                        {**params, "_lim": page_size, "_off": (page_no - 1) * page_size}).mappings()
    return total, [dict(r) for r in rows]


# ------------------------------------------------------------------ reference data
def cbse_students(conn, class_passed=None, exam_year=None, district=None, page_no=1, page_size=50):
    where, p = [], {}
    if class_passed:
        where.append("class_passed = :c"); p["c"] = class_passed
    if exam_year:
        where.append("exam_year = :y"); p["y"] = exam_year
    if district:
        where.append("district = :d"); p["d"] = district
    sql = "SELECT roll_no, exam_year, apaar_id, candidate_name, dob_raw, dob_iso, gender, father_name, mother_name, " \
          "class_passed, school, district, mobile FROM cbse_results"
    if where:
        sql += " WHERE " + " AND ".join(where)
    return page(conn, sql, p, "roll_no", page_no, page_size)


def cbse_student(conn, roll_no: str) -> Optional[dict]:
    r = conn.execute(text("SELECT * FROM cbse_results WHERE roll_no = :r"), {"r": roll_no}).mappings().first()
    return dict(r) if r else None


JA_COLS = ("member_id, jan_aadhaar_id, name_eng, dob_raw, dob_iso, gender, gender_norm, father_name_eng, "
           "mother_name_eng, category, annual_family_income, district, domicile_state, relation")


def ja_candidates(conn, dob: str, gender: Optional[str] = None, district: Optional[str] = None, limit: int = 200):
    """Server-side blocking query: DOB (Level-1 normalised) [+ gender] [+ district]."""
    dob_iso = l1_dob(dob)
    if not dob_iso:
        raise ValueError(f"could not parse dob '{dob}'")
    where, p = ["dob_iso = :dob"], {"dob": dob_iso, "n": limit}
    if gender:
        g = l1_gender(gender)
        if not g:
            raise ValueError(f"could not parse gender '{gender}'")
        where.append("gender_norm = :g"); p["g"] = g
    if district:
        where.append("LOWER(district) = LOWER(:d)"); p["d"] = district
    rows = conn.execute(text(f"SELECT {JA_COLS} FROM jan_aadhaar_members WHERE {' AND '.join(where)} "
                             "ORDER BY member_id LIMIT :n"), p).mappings()
    return dob_iso, [dict(r) for r in rows]


def ja_member(conn, member_id: str) -> Optional[dict]:
    r = conn.execute(text("SELECT * FROM jan_aadhaar_members WHERE member_id = :m"), {"m": member_id}).mappings().first()
    return dict(r) if r else None


def schemes(conn, level=None, state=None, active=None, q=None, page_no=1, page_size=100):
    where, p = [], {}
    if level:
        where.append("scheme_level = :l"); p["l"] = level
    if state:
        where.append("LOWER(scheme_state_ut) = LOWER(:s)"); p["s"] = state
    if active is not None:
        where.append("active_status = :a"); p["a"] = "ACTIVE" if active else "EXCLUDED"
    if q:
        where.append("LOWER(scheme_name) LIKE :q"); p["q"] = f"%{q.lower()}%"
    sql = "SELECT scheme_id, rule_json FROM scheme_rules"
    if where:
        sql += " WHERE " + " AND ".join(where)
    total, rows = page(conn, sql, p, "master_row", page_no, page_size)
    return total, [json.loads(r["rule_json"]) for r in rows]


# ------------------------------------------------------------------ results
def decisions(conn, run_id, band=None, scenario=None, page_no=1, page_size=500):
    where, p = ["run_id = :r"], {"r": run_id}
    if band:
        where.append("linkage_band = :b"); p["b"] = band
    if scenario:
        where.append("scenario = :s"); p["s"] = scenario
    total, rows = page(conn, "SELECT roll_no, detail_json FROM link_decisions WHERE " + " AND ".join(where), p,
                       "roll_no", page_no, page_size)
    return total, [json.loads(r["detail_json"]) for r in rows]


def all_decisions(conn, run_id) -> list[dict]:
    return [json.loads(r[0]) for r in conn.execute(
        text("SELECT detail_json FROM link_decisions WHERE run_id = :r ORDER BY roll_no"), {"r": run_id})]


def decision(conn, run_id, roll_no) -> Optional[dict]:
    r = conn.execute(text("SELECT detail_json FROM link_decisions WHERE run_id = :r AND roll_no = :n"),
                     {"r": run_id, "n": roll_no}).first()
    return json.loads(r[0]) if r else None


def student_summary(conn, run_id, student_id) -> Optional[dict]:
    r = conn.execute(text("SELECT detail_json FROM student_eligibility WHERE run_id = :r AND student_id = :s"),
                     {"r": run_id, "s": student_id}).first()
    return json.loads(r[0]) if r else None


def student_summaries(conn, run_id) -> list[dict]:
    return [json.loads(r[0]) for r in conn.execute(
        text("SELECT detail_json FROM student_eligibility WHERE run_id = :r ORDER BY student_id"), {"r": run_id})]


def student_results(conn, run_id, student_id, include_failed=False) -> list[dict]:
    sql = ("SELECT e.scheme_id, e.domicile_result, e.education_stage_result, e.social_category_result, "
           "e.gender_result, e.income_result, e.age_result, e.final_result, e.failure_reason, s.rule_json "
           "FROM eligibility_results e LEFT JOIN scheme_rules s ON s.scheme_id = e.scheme_id "
           "WHERE e.run_id = :r AND e.student_id = :s")
    if not include_failed:
        sql += " AND e.final_result = 'ELIGIBLE'"
    out = []
    for r in conn.execute(text(sql + " ORDER BY e.scheme_id"), {"r": run_id, "s": student_id}).mappings():
        d = dict(r)
        rule = json.loads(d.pop("rule_json") or "{}")
        d.update({k: rule.get(k) for k in ("Scheme_Name", "Scheme_Level", "Scheme_State_UT", "Education_Stage_Allowed",
                                           "Categories_Allowed", "Gender_Allowed", "Income_Raw", "Age_Raw",
                                           "Application_Portal", "Benefits", "Source_URL")})
        out.append(d)
    return out


def outreach(conn, run_id, status=None, page_no=1, page_size=500):
    where, p = ["run_id = :r"], {"r": run_id}
    if status:
        where.append("outreach_status = :s"); p["s"] = status
    total, rows = page(conn, "SELECT roll_no, outreach_status, detail_json FROM outreach_queue WHERE " +
                       " AND ".join(where), p, "outreach_status, roll_no", page_no, page_size)
    return total, [json.loads(r["detail_json"]) for r in rows]
