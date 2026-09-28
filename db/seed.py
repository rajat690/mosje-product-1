"""Load the synthetic CSVs (data/*.csv or *.csv.gz) and the scheme master xlsx into the database.

Idempotent: each dataset's SHA-256 is stored in seed_meta; if nothing changed the seed is skipped.
A changed dataset (or force=True) reloads ALL inputs and clears old pipeline results, all in one
transaction. Usage:  python -m db.seed [--force]
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

from mosje import config
from mosje.normalize import l1_dob, l1_gender
from mosje.rules_compiler import compile_row, load_master

from .bulk import bulk_insert
from .engine import get_engine
from .migrate import migrate

log = logging.getLogger("mosje.seed")
EXAM_YEAR = "2025-26"
DATASETS = {"jan_aadhaar_members": "jan_aadhaar_members.csv", "cbse_results": "cbse_passed_2025_26.csv",
            "ground_truth": "ground_truth.csv"}
INPUT_TABLES = ("jan_aadhaar_members", "cbse_results", "ground_truth", "scheme_master", "scheme_rules")
RESULT_TABLES = ("eligibility_results", "student_eligibility", "outreach_queue", "link_decisions", "pipeline_runs")


def _find(name: str, data_dir: Path) -> Path | None:
    for cand in (data_dir / (name + ".gz"), data_dir / name):
        if cand.exists():
            return cand
    return None


def read_csv_any(path: Path) -> list[dict]:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)
    return list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))


def _sha(path: Path) -> str:
    raw = path.read_bytes()
    if path.suffix == ".gz":
        raw = gzip.decompress(raw)          # checksum of content, not of the compression
    return hashlib.sha256(raw).hexdigest()


def _nz(v):
    v = "" if v is None else str(v)
    return v if v != "" else None


def rules_rows(master_rows: list[dict], now) -> list[tuple]:
    out = []
    for i, r in enumerate(master_rows, start=1):
        rule = compile_row(r, i)
        e = rule.export_dict()
        out.append((rule.Scheme_ID, i, rule.Scheme_Name, rule.Scheme_Level, rule.Scheme_State_UT, rule.Active_Status,
                    rule.Compile_Status, rule.Education_Stage_Status, rule.Age_Status, rule.Gender_Status,
                    rule.Income_Status, rule.Category_Status, rule.Rule_Version,
                    json.dumps(e, default=str, ensure_ascii=False), now))
    return out


RULE_COLS = ("scheme_id", "master_row", "scheme_name", "scheme_level", "scheme_state_ut", "active_status",
             "compile_status", "education_stage_status", "age_status", "gender_status", "income_status",
             "category_status", "rule_version", "rule_json", "compiled_at")


def seed(engine: Engine | None = None, force: bool = False, data_dir: Path | None = None) -> dict:
    engine = engine or get_engine()
    migrate(engine)
    data_dir = Path(data_dir or config.DATA_DIR)
    paths = {k: _find(v, data_dir) for k, v in DATASETS.items()}
    missing = [DATASETS[k] for k, p in paths.items() if p is None and k != "ground_truth"]
    master_path = Path(config.SCHEME_MASTER_PATH)
    if not master_path.exists():
        missing.append(str(master_path))
    if missing:
        raise FileNotFoundError(f"seed input files not found: {missing} (looked in {data_dir})")
    sums = {k: _sha(p) for k, p in paths.items() if p}
    sums["scheme_master"] = hashlib.sha256(master_path.read_bytes()).hexdigest()

    with engine.connect() as conn:
        meta = {r[0]: r[1] for r in conn.execute(text("SELECT dataset, checksum FROM seed_meta"))}
        counts = {t: conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar() for t in INPUT_TABLES}
    if not force and meta == sums and counts["jan_aadhaar_members"] and counts["scheme_rules"]:
        return {"status": "skipped", "reason": "already seeded with identical data", "counts": counts}

    now = datetime.now(timezone.utc)
    ja = read_csv_any(paths["jan_aadhaar_members"])
    cbse = read_csv_any(paths["cbse_results"])
    truth = read_csv_any(paths["ground_truth"]) if paths["ground_truth"] else []
    master = load_master(master_path)
    loaded = {}
    with engine.begin() as conn:
        for t in RESULT_TABLES + INPUT_TABLES + ("seed_meta",):
            conn.execute(text(f"DELETE FROM {t}"))
        loaded["jan_aadhaar_members"] = bulk_insert(conn, "jan_aadhaar_members", (
            "member_id", "jan_aadhaar_id", "name_eng", "name_hnd", "dob_raw", "dob_iso", "gender", "gender_norm",
            "father_name_eng", "mother_name_eng", "category", "annual_family_income", "district", "domicile_state",
            "disability", "mobile", "relation", "loaded_at"), (
            (m["member_id"], m["jan_aadhaar_id"], _nz(m["nameEng"]), _nz(m["nameHnd"]), _nz(m["dob"]),
             l1_dob(m["dob"]), _nz(m["gender"]), l1_gender(m["gender"]), _nz(m["fatherNameEng"]),
             _nz(m["motherNameEng"]), _nz(m["category"]), _nz(m["annual_family_income"]), _nz(m["district"]),
             _nz(m["domicile_state"]), _nz(m["disability"]), _nz(m["mobile"]), _nz(m["relation"]), now)
            for m in ja))
        loaded["cbse_results"] = bulk_insert(conn, "cbse_results", (
            "roll_no", "exam_year", "apaar_id", "candidate_name", "dob_raw", "dob_iso", "gender", "father_name",
            "mother_name", "class_passed", "school", "district", "mobile", "loaded_at"), (
            (c["roll_no"], EXAM_YEAR, _nz(c["apaar_id"]), _nz(c["candidate_name"]), _nz(c["dob"]), l1_dob(c["dob"]),
             _nz(c["gender"]), _nz(c["father_name"]), _nz(c["mother_name"]), _nz(c["class_passed"]),
             _nz(c["school"]), _nz(c["district"]), _nz(c["mobile"]), now) for c in cbse))
        loaded["ground_truth"] = bulk_insert(conn, "ground_truth", (
            "roll_no", "true_member_id", "in_jan_aadhaar", "class_passed", "noise_types", "has_lookalike_or_twin"), (
            (t["roll_no"], _nz(t["true_member_id"]), _nz(t["in_jan_aadhaar"]), _nz(t["class_passed"]),
             _nz(t["noise_types"]), _nz(t["has_lookalike_or_twin"])) for t in truth))
        loaded["scheme_master"] = bulk_insert(conn, "scheme_master", (
            "master_row", "scheme_name", "level", "state_ut", "verification_status", "raw_json", "source_file",
            "loaded_at"), (
            (i, _nz(r.get("Programme / Scheme Name")), _nz(r.get("Level")), _nz(r.get("State / UT / Central")),
             _nz(r.get("Verification Status")), json.dumps(r, default=str, ensure_ascii=False), master_path.name, now)
            for i, r in enumerate(master, start=1)))
        loaded["scheme_rules"] = bulk_insert(conn, "scheme_rules", RULE_COLS, rules_rows(master, now))
        rc = dict(loaded, scheme_master=len(master))
        for k, v in sums.items():
            conn.execute(text("INSERT INTO seed_meta (dataset, checksum, row_count, loaded_at) VALUES (:d, :c, :n, :t)"),
                         {"d": k, "c": v, "n": rc.get(k, 0), "t": now})
    log.info("seeded %s", loaded)
    return {"status": "seeded", "counts": loaded}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="reload even if the data has not changed")
    print(json.dumps(seed(force=ap.parse_args().force), indent=2, default=str))
