"""Runs the MoSJE engine inside the API process: DB (repository) -> mosje.pipeline.compute -> DB.

The engine code is the unchanged prototype package (mosje/). Only the IO differs: inputs come from
the database tables instead of CSV files and results are written to result tables.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.engine import Engine

from db import repository as repo
from db.bulk import bulk_insert
from db.seed import RULE_COLS, rules_rows
from mosje.pipeline import compute
from mosje.rules_compiler import compile_row

log = logging.getLogger("mosje.pipeline")
_LOCK = threading.Lock()
RESULT_TABLES = ("eligibility_results", "student_eligibility", "outreach_queue", "link_decisions")


class PipelineBusy(RuntimeError):
    pass


def _f(v):
    try:
        return None if v in (None, "") else float(v)
    except (TypeError, ValueError):
        return None


def new_run(engine: Engine, triggered_by: str = "api") -> str:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    with engine.begin() as conn:
        busy = conn.execute(text("SELECT run_id FROM pipeline_runs WHERE status IN ('QUEUED','RUNNING')")).first()
        if busy:
            raise PipelineBusy(f"run {busy[0]} is already in progress")
        conn.execute(text("INSERT INTO pipeline_runs (run_id, status, started_at, triggered_by) "
                          "VALUES (:r, 'QUEUED', :t, :b)"), {"r": run_id, "t": datetime.now(timezone.utc), "b": triggered_by})
    return run_id


def execute_run(engine: Engine, run_id: str, sensitivity: bool | None = None) -> dict:
    """Blocking run. Safe to call from a background thread."""
    if sensitivity is None:
        sensitivity = os.environ.get("PIPELINE_SENSITIVITY", "false").lower() == "true"
    if not _LOCK.acquire(blocking=False):
        _fail(engine, run_id, "another run is executing in this process")
        raise PipelineBusy("another run is executing in this process")
    t0 = time.time()
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE pipeline_runs SET status='RUNNING' WHERE run_id=:r"), {"r": run_id})
        with engine.connect() as conn:
            ja = repo.load_ja_for_engine(conn)
            cbse = repo.load_cbse_for_engine(conn)
            truth = repo.load_truth_for_engine(conn)
            master = repo.load_master_rows(conn)
        if not ja or not cbse or not master:
            raise RuntimeError("database is not seeded (run POST /admin/seed first)")
        rules = [compile_row(r, i) for i, r in enumerate(master, start=1)]
        log.info("run %s: loaded %d JA, %d CBSE, %d GT, %d scheme rows from DB", run_id, len(ja), len(cbse),
                 len(truth), len(rules))
        c = compute(ja, cbse, truth, rules, log=log.info, t0=t0, sensitivity=sensitivity)
        del ja
        import gc
        gc.collect()
        _write_results(engine, run_id, c, master)
        res = c["results"]
        res["runtime_seconds"] = round(time.time() - t0, 1)
        summary = {"results": res, "coverage": c["coverage"], "top_schemes": c["top_schemes"],
                   "input_counts": {"cbse": len(cbse), "ground_truth": len(truth), "scheme_rows": len(rules)}}
        with engine.begin() as conn:
            conn.execute(text("UPDATE pipeline_runs SET status='SUCCEEDED', finished_at=:t, results_json=:j "
                              "WHERE run_id=:r"),
                         {"t": datetime.now(timezone.utc), "j": json.dumps(summary, default=str), "r": run_id})
        log.info("run %s succeeded in %.1fs", run_id, time.time() - t0)
        return summary
    except Exception as e:  # noqa: BLE001 - record any failure on the run row
        log.error("run %s failed: %s", run_id, traceback.format_exc())
        _fail(engine, run_id, f"{type(e).__name__}: {e}")
        raise
    finally:
        _LOCK.release()


def _fail(engine, run_id, msg):
    with engine.begin() as conn:
        conn.execute(text("UPDATE pipeline_runs SET status='FAILED', finished_at=:t, error=:e WHERE run_id=:r"),
                     {"t": datetime.now(timezone.utc), "e": msg[:4000], "r": run_id})


def _write_results(engine: Engine, run_id: str, c: dict, master: list[dict]):
    keep = os.environ.get("KEEP_OLD_RESULTS", "false").lower() == "true"
    now = datetime.now(timezone.utc)
    cls_by_roll = {d["Roll_No"]: d["Class"] for d in c["decisions"]}
    with engine.begin() as conn:
        if not keep:                       # keep the database small (free Postgres = 1 GB)
            for t in RESULT_TABLES:
                conn.execute(text(f"DELETE FROM {t}"))
        conn.execute(text("DELETE FROM scheme_rules"))
        bulk_insert(conn, "scheme_rules", RULE_COLS, rules_rows(master, now))
        bulk_insert(conn, "link_decisions", (
            "run_id", "roll_no", "class_passed", "match_method", "candidates_generated", "best_member_id", "name_sim",
            "dob_result", "father_sim", "mother_sim", "gender_result", "overall_score", "second_member_id",
            "second_best_score", "margin", "g7_status", "scenario", "classification", "matrix_action", "final_action",
            "linkage_band", "flag_reason", "linked_member_id", "outreach_status", "gt_true_member_id", "gt_outcome",
            "detail_json"), (
            (run_id, d["Roll_No"], d["Class"], d["Match_Method"], int(d["Candidates_Generated"] or 0),
             d["Best_Member_ID"] or None, _f(d["Name_Sim_%"]), d["DOB"] or None, _f(d["Father_Sim_%"]),
             _f(d["Mother_Sim_%"]), d["Gender"] or None, _f(d["Overall_Score"]), d["Second_Member_ID"] or None,
             _f(d["Second_Best_Score"]), _f(d["Margin"]), d["G7"], d["Scenario"], d["Classification"],
             d["Matrix_Action"], d["Final_Action"], d["Linkage_Band"], d["Flag_Reason"],
             d["Linked_Member_ID"] or None, d["Outreach_Status"], d["GT_True_Member_ID"] or None, d["GT_Outcome"],
             json.dumps(d, default=str, ensure_ascii=False)) for d in c["decisions"]))
        bulk_insert(conn, "student_eligibility", (
            "run_id", "student_id", "member_id", "class_passed", "total_checked", "eligible_count",
            "eligible_scheme_ids", "outreach_status", "detail_json"), (
            (run_id, s["Student_ID"], s["Member_ID"], cls_by_roll.get(s["Student_ID"]),
             s["Total_Candidate_Schemes_Checked"], s["Eligible_Scheme_Count"], s["Eligible_Scheme_IDs"],
             s["Outreach_Status"], json.dumps(s, default=str, ensure_ascii=False)) for s in c["summaries"]))
        bulk_insert(conn, "eligibility_results", (
            "run_id", "student_id", "scheme_id", "domicile_result", "education_stage_result", "social_category_result",
            "gender_result", "income_result", "age_result", "final_result", "failure_reason"), (
            (run_id, a["Student_ID"], a["Scheme_ID"], a["Domicile_Result"], a["Education_Stage_Result"],
             a["Social_Category_Result"], a["Gender_Result"], a["Income_Result"], a["Age_Result"], a["Final_Result"],
             a["Failure_Reason"]) for a in c["audits"]))
        bulk_insert(conn, "outreach_queue", (
            "run_id", "roll_no", "outreach_status", "message_type", "template_name", "mobile", "sendable",
            "eligible_scheme_count", "detail_json"), (
            (run_id, q["Roll_No"], q["Outreach_Status"], q["Message_Type"], q["Template_Name"], q["Mobile"],
             q["Sendable"], int(q["Eligible_Scheme_Count"]) if str(q["Eligible_Scheme_Count"]).isdigit() else None,
             json.dumps(q, default=str, ensure_ascii=False)) for q in c["queue"]))


def start_background(engine: Engine, triggered_by: str = "api") -> str:
    run_id = new_run(engine, triggered_by)
    threading.Thread(target=lambda: _safe(engine, run_id), name=f"pipeline-{run_id}", daemon=True).start()
    return run_id


def _safe(engine, run_id):
    try:
        execute_run(engine, run_id)
    except Exception:  # noqa: BLE001 - already recorded on the run row
        pass
