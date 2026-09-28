"""MoSJE Product 1 platform API.

Architecture: dashboard -> this API -> database. The linkage + eligibility pipeline runs inside
this process (background thread), reading inputs from the DB and writing results back.

Auth: every endpoint except /health, /docs, /redoc and /openapi.json needs header X-API-Key
equal to the API_KEY environment variable.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Literal, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import text

from db import repository as repo
from db.engine import get_engine, is_postgres
from db.migrate import migrate
from db.seed import seed
from mosje import config
from mosje.match_outcomes import payload as match_outcomes_payload
from mosje.scenarios36 import export_rows as s36_export, scenarios36, summary as s36_summary
from mosje.scenarios import scenario_outcomes, summary as scenario_summary

from . import pipeline_service as ps

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
log = logging.getLogger("mosje.api")
VERSION = "1.0.0"
STATE = {"startup": "not started", "startup_error": None}


def _flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def _startup_tasks():
    """Runs in a background thread so the web server answers /health immediately."""
    eng = get_engine()
    try:
        STATE["startup"] = "migrating"
        migrate(eng)
        with eng.begin() as conn:     # runs interrupted by a restart can never finish
            conn.execute(text("UPDATE pipeline_runs SET status='FAILED', error='interrupted (service restarted)', "
                              "finished_at=:t WHERE status IN ('QUEUED','RUNNING')"), {"t": datetime.now(timezone.utc)})
        if _flag("AUTO_SEED"):
            STATE["startup"] = "seeding"
            log.info("AUTO_SEED: %s", seed(eng)["status"])
        if _flag("AUTO_RUN_PIPELINE"):
            with eng.connect() as conn:
                has_run = repo.latest_run(conn) is not None
                seeded = conn.execute(text("SELECT COUNT(*) FROM cbse_results")).scalar() > 0
            if seeded and not has_run:
                STATE["startup"] = "running pipeline"
                rid = ps.new_run(eng, "auto-startup")
                ps.execute_run(eng, rid)
        STATE["startup"] = "ready"
    except Exception as e:  # noqa: BLE001
        log.exception("startup task failed")
        STATE["startup"], STATE["startup_error"] = "error", f"{type(e).__name__}: {e}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not os.environ.get("API_KEY"):
        log.warning("API_KEY is not set: every protected endpoint will return 503 until it is configured")
    if _flag("RUN_STARTUP_TASKS", "true"):
        threading.Thread(target=_startup_tasks, name="startup", daemon=True).start()
    yield


app = FastAPI(
    title="MoSJE Product 1 – Scholarship Intelligence API",
    version=VERSION,
    description="Record linkage (CBSE ↔ Jan Aadhaar, Linkage Rules V3.0) + scholarship eligibility "
                "(Eligibility Rule V3.0) on **synthetic data**. Click **Authorize** and paste the API key "
                "(header `X-API-Key`) to try the endpoints.",
    lifespan=lifespan,
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False, description="Value of the API_KEY env var")


def require_key(key: Optional[str] = Security(api_key_header)):
    expected = os.environ.get("API_KEY")
    if not expected:
        raise HTTPException(503, "API_KEY is not configured on the server")
    if not key or not hmac.compare_digest(key, expected):
        raise HTTPException(401, "missing or invalid X-API-Key header")
    return True


def conn():
    with get_engine().connect() as c:
        yield c


def latest_or_404(c):
    run = repo.latest_run(c)
    if not run:
        raise HTTPException(404, "no successful pipeline run yet – call POST /pipeline/run first")
    return run


class Page(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[dict]


# ------------------------------------------------------------------ public
@app.get("/", include_in_schema=False)
def root():
    return {"service": "mosje-api", "version": VERSION, "docs": "/docs", "health": "/health"}


@app.get("/health", tags=["system"])
def health():
    """Liveness + readiness. No API key needed (used by Render health checks)."""
    out = {"status": "ok", "version": VERSION, "startup": STATE["startup"], "startup_error": STATE["startup_error"],
           "rule_version": config.RULE_VERSION}
    try:
        eng = get_engine()
        with eng.connect() as c:
            c.execute(text("SELECT 1"))
            out["database"] = "postgresql" if is_postgres(eng) else eng.dialect.name
            try:
                out["seeded"] = c.execute(text("SELECT COUNT(*) FROM cbse_results")).scalar() > 0
                run = repo.latest_run(c, succeeded_only=False)
                out["latest_run"] = {k: run[k] for k in ("run_id", "status", "started_at", "finished_at")} if run else None
            except Exception:  # noqa: BLE001 - tables not created yet
                out["seeded"] = False
    except Exception as e:  # noqa: BLE001
        out.update(status="degraded", database_error=str(e)[:300])
    return out


# ------------------------------------------------------------------ admin
@app.post("/admin/seed", tags=["admin"], dependencies=[Depends(require_key)])
def admin_seed(force: bool = Query(False, description="reload even if the data is unchanged (clears results)")):
    """Create tables (if needed) and load the synthetic CSVs + scheme master into the database. Idempotent."""
    try:
        return seed(get_engine(), force=force)
    except FileNotFoundError as e:
        raise HTTPException(500, str(e))


@app.get("/admin/status", tags=["admin"], dependencies=[Depends(require_key)])
def admin_status(c=Depends(conn)):
    return {"counts": repo.counts(c), "runs": repo.list_runs(c, 10), "startup": STATE}


# ------------------------------------------------------------------ inputs
@app.get("/cbse/students", tags=["inputs"], response_model=Page, dependencies=[Depends(require_key)])
def cbse_students(class_passed: Optional[Literal["X", "XII"]] = Query(None, alias="class"),
                  year: Optional[str] = Query(None, description="exam year, e.g. 2025-26"),
                  district: Optional[str] = None, page: int = Query(1, ge=1),
                  page_size: int = Query(50, ge=1, le=1000), c=Depends(conn)):
    total, items = repo.cbse_students(c, class_passed, year, district, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/cbse/students/{roll_no}", tags=["inputs"], dependencies=[Depends(require_key)])
def cbse_student(roll_no: str, c=Depends(conn)):
    r = repo.cbse_student(c, roll_no)
    if not r:
        raise HTTPException(404, "roll number not found")
    return r


@app.get("/jan-aadhaar/candidates", tags=["inputs"], dependencies=[Depends(require_key)])
def ja_candidates(dob: str = Query(..., description="any common format, e.g. 2009-04-07 or 07 Apr 2009"),
                  gender: Optional[str] = None, district: Optional[str] = None,
                  limit: int = Query(200, ge=1, le=2000), c=Depends(conn)):
    """Server-side blocking query (Linkage Rules V3.0 pass 1: DOB + gender), optional district filter."""
    try:
        dob_iso, items = repo.ja_candidates(c, dob, gender, district, limit)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"dob_normalised": dob_iso, "count": len(items), "items": items}


@app.get("/jan-aadhaar/members/{member_id}", tags=["inputs"], dependencies=[Depends(require_key)])
def ja_member(member_id: str, c=Depends(conn)):
    r = repo.ja_member(c, member_id)
    if not r:
        raise HTTPException(404, "member not found")
    return r


@app.get("/schemes", tags=["inputs"], response_model=Page, dependencies=[Depends(require_key)])
def schemes(level: Optional[Literal["Central", "State/UT"]] = None, state: Optional[str] = None,
            active: Optional[bool] = None, q: Optional[str] = Query(None, description="text in scheme name"),
            page: int = Query(1, ge=1), page_size: int = Query(100, ge=1, le=1000), c=Depends(conn)):
    """Compiled scheme rules (one per master row) with per-field parse status."""
    total, items = repo.schemes(c, level, state, active, q, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


# ------------------------------------------------------------------ pipeline
@app.post("/pipeline/run", tags=["pipeline"], dependencies=[Depends(require_key)])
def pipeline_run(wait: bool = Query(False, description="true = block until finished (may take 1–3 min on free plan)")):
    """Run linkage + eligibility + outreach on the data in the DB and store the results."""
    eng = get_engine()
    try:
        if wait:
            rid = ps.new_run(eng, "api-sync")
            try:
                ps.execute_run(eng, rid)
            except ps.PipelineBusy as e:
                raise HTTPException(409, str(e))
            except Exception as e:  # noqa: BLE001
                raise HTTPException(500, f"pipeline failed: {e}")
            with eng.connect() as c:
                return repo.get_run(c, rid)
        rid = ps.start_background(eng, "api")
    except ps.PipelineBusy as e:
        raise HTTPException(409, str(e))
    return {"run_id": rid, "status": "QUEUED", "poll": f"/pipeline/runs/{rid}"}


@app.get("/pipeline/runs", tags=["pipeline"], dependencies=[Depends(require_key)])
def pipeline_runs(c=Depends(conn)):
    return repo.list_runs(c, 20)


@app.get("/pipeline/runs/{run_id}", tags=["pipeline"], dependencies=[Depends(require_key)])
def pipeline_run_status(run_id: str, c=Depends(conn)):
    r = repo.get_run(c, run_id)
    if not r:
        raise HTTPException(404, "run not found")
    return r


# ------------------------------------------------------------------ results
@app.get("/results/funnel", tags=["results"], dependencies=[Depends(require_key)])
def results_funnel(c=Depends(conn)):
    """Funnel, match quality, eligibility stats and headline counts of the latest successful run."""
    run = latest_or_404(c)
    r = run["results"]["results"]
    return {"run_id": run["run_id"], "finished_at": run["finished_at"], "funnel": r["funnel"],
            "quality": r["quality"], "eligibility_stats": r["eligibility_stats"], "rule_stats": r["rule_stats"],
            "action_counts": r["action_counts"], "band_counts": r["band_counts"],
            "outreach_counts": r["outreach_counts"], "counts": r["counts"], "generated_at": r["generated_at"],
            "rule_version": r["rule_version"], "eligibility_as_of_date": r["eligibility_as_of_date"],
            "sensitivity": r.get("sensitivity"), "sensitivity_bands": r.get("sensitivity_bands"),
            "runtime_seconds": r.get("runtime_seconds")}


@app.get("/results/match-outcomes", tags=["results"], dependencies=[Depends(require_key)])
def results_match_outcomes(c=Depends(conn)):
    """The six headline linkage outcomes vs ground truth (true matches found, false matches, missed matches,
    precision, recall, false-positive rate), each with its formula and a plain-English definition."""
    run = latest_or_404(c)
    r = run["results"]["results"]
    return {"run_id": run["run_id"], "generated_at": r.get("generated_at"), **match_outcomes_payload(r["quality"])}


@app.get("/results/scenarios", tags=["results"], dependencies=[Depends(require_key)])
def results_scenarios(c=Depends(conn)):
    """All 56 matrix scenarios + EXACT path + NO_CANDIDATE + DEFAULT with TP/FP/FN/TN and G7-blocked counts
    (computed live from link_decisions of the latest run)."""
    run = latest_or_404(c)
    rows = scenario_outcomes(repo.all_decisions(c, run["run_id"]))
    return {"run_id": run["run_id"], "summary": scenario_summary(rows), "rows": rows}


@app.get("/results/scenarios-36", tags=["results"], dependencies=[Depends(require_key)])
def results_scenarios_36(c=Depends(conn)):
    """REPORTING VIEW ONLY: the earlier 36-row decision matrix (original columns verbatim) with every record of the
    latest run classified against it (first matching row wins, using the field scores V3.0 computed) and
    ground-truth outcome counts of the link V3.0 actually made. Adds NO_CANDIDATE and NOT_LISTED rows.
    V3.0 decides every link; this endpoint changes nothing."""
    run = latest_or_404(c)
    rows = scenarios36(repo.all_decisions(c, run["run_id"]))
    return {"run_id": run["run_id"], "summary": s36_summary(rows), "rows": s36_export(rows)}


@app.get("/results/coverage", tags=["results"], dependencies=[Depends(require_key)])
def results_coverage(c=Depends(conn)):
    run = latest_or_404(c)
    return {"run_id": run["run_id"], "rows": run["results"]["coverage"]}


@app.get("/results/top-schemes", tags=["results"], dependencies=[Depends(require_key)])
def results_top_schemes(c=Depends(conn)):
    run = latest_or_404(c)
    return {"run_id": run["run_id"], "rows": run["results"]["top_schemes"]}


@app.get("/results/decisions", tags=["results"], response_model=Page, dependencies=[Depends(require_key)])
def results_decisions(band: Optional[Literal["MATCHED", "PROBABLE", "NOT MATCHED"]] = None,
                      scenario: Optional[str] = None, page: int = Query(1, ge=1),
                      page_size: int = Query(500, ge=1, le=10000), c=Depends(conn)):
    run = latest_or_404(c)
    total, items = repo.decisions(c, run["run_id"], band, scenario, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/results/eligibility-summary", tags=["results"], dependencies=[Depends(require_key)])
def results_eligibility_summary(c=Depends(conn)):
    run = latest_or_404(c)
    return {"run_id": run["run_id"], "rows": repo.student_summaries(c, run["run_id"])}


@app.get("/student/{student_id}", tags=["results"], dependencies=[Depends(require_key)])
def student(student_id: str, c=Depends(conn)):
    """CBSE record + linkage decision (+ best Jan Aadhaar candidate) for one roll number."""
    run = latest_or_404(c)
    d = repo.decision(c, run["run_id"], student_id)
    if not d:
        raise HTTPException(404, "student not found in latest run")
    best = repo.ja_member(c, d["Best_Member_ID"]) if d.get("Best_Member_ID") else None
    return {"run_id": run["run_id"], "cbse": repo.cbse_student(c, student_id), "decision": d, "best_candidate": best}


@app.get("/student/{student_id}/eligible-schemes", tags=["results"], dependencies=[Depends(require_key)])
def student_schemes(student_id: str, include_failed: bool = False, c=Depends(conn)):
    """Eligible schemes (all six checks PASS) for a linked student; include_failed=true adds the audit rows."""
    run = latest_or_404(c)
    d = repo.decision(c, run["run_id"], student_id)
    if not d:
        raise HTTPException(404, "student not found in latest run")
    s = repo.student_summary(c, run["run_id"], student_id)
    return {"run_id": run["run_id"], "student_id": student_id, "linkage_band": d["Linkage_Band"],
            "linked_member_id": d["Linked_Member_ID"] or None, "summary": s,
            "note": None if s else "not linked: eligibility engine not run (no Jan Aadhaar enrichment)",
            "schemes": repo.student_results(c, run["run_id"], student_id, include_failed) if s else []}


@app.get("/outreach/queue", tags=["results"], response_model=Page, dependencies=[Depends(require_key)])
def outreach_queue(type: Optional[Literal["eligible", "discovery"]] = Query(None, description="eligible or discovery"),
                   page: int = Query(1, ge=1), page_size: int = Query(500, ge=1, le=10000), c=Depends(conn)):
    run = latest_or_404(c)
    status = {"eligible": "QUEUE_FOR_OUTREACH", "discovery": "QUEUE_FOR_DISCOVERY_OUTREACH"}.get(type)
    total, items = repo.outreach(c, run["run_id"], status, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}
