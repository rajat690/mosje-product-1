-- MoSJE Product 1 platform: initial schema.
-- Portable SQL (runs on PostgreSQL 14+ and on SQLite for tests). Applied by db/migrate.py,
-- which records applied files in schema_migrations. Never edit an applied migration:
-- add 002_*.sql instead.

-- =========================================================== INPUT TABLES
CREATE TABLE IF NOT EXISTS jan_aadhaar_members (
    member_id              TEXT PRIMARY KEY,
    jan_aadhaar_id         TEXT NOT NULL,
    name_eng               TEXT,
    name_hnd               TEXT,
    dob_raw                TEXT,
    dob_iso                TEXT,            -- Level-1 normalised YYYY-MM-DD (blocking key)
    gender                 TEXT,
    gender_norm            TEXT,            -- Level-1 normalised gender (blocking key)
    father_name_eng        TEXT,
    mother_name_eng        TEXT,
    category               TEXT,
    annual_family_income   TEXT,
    district               TEXT,
    domicile_state         TEXT,
    disability             TEXT,
    mobile                 TEXT,
    relation               TEXT,
    loaded_at              TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_ja_dob_gender ON jan_aadhaar_members (dob_iso, gender_norm);
CREATE INDEX IF NOT EXISTS ix_ja_district ON jan_aadhaar_members (district);
CREATE INDEX IF NOT EXISTS ix_ja_family ON jan_aadhaar_members (jan_aadhaar_id);

CREATE TABLE IF NOT EXISTS cbse_results (
    roll_no                TEXT PRIMARY KEY,
    exam_year              TEXT NOT NULL,   -- e.g. 2025-26
    apaar_id               TEXT,
    candidate_name         TEXT,
    dob_raw                TEXT,
    dob_iso                TEXT,
    gender                 TEXT,
    father_name            TEXT,
    mother_name            TEXT,
    class_passed           TEXT,            -- X / XII
    school                 TEXT,
    district               TEXT,
    mobile                 TEXT,
    loaded_at              TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_cbse_class_year ON cbse_results (class_passed, exam_year);

-- Synthetic-data evaluation only (real data has no ground truth; leave empty).
CREATE TABLE IF NOT EXISTS ground_truth (
    roll_no                TEXT PRIMARY KEY,
    true_member_id         TEXT,
    in_jan_aadhaar         TEXT,
    class_passed           TEXT,
    noise_types            TEXT,
    has_lookalike_or_twin  TEXT
);

-- Raw scheme master rows exactly as read from the xlsx (one JSON object per row).
CREATE TABLE IF NOT EXISTS scheme_master (
    master_row             INTEGER PRIMARY KEY,
    scheme_name            TEXT,
    level                  TEXT,
    state_ut               TEXT,
    verification_status    TEXT,
    raw_json               TEXT NOT NULL,
    source_file            TEXT,
    loaded_at              TIMESTAMP
);

-- Compiled machine-checkable rules (Eligibility Rule V3.0, 7.1), rebuilt on seed and on every run.
CREATE TABLE IF NOT EXISTS scheme_rules (
    scheme_id              TEXT PRIMARY KEY,
    master_row             INTEGER,
    scheme_name            TEXT,
    scheme_level           TEXT,
    scheme_state_ut        TEXT,
    active_status          TEXT,
    compile_status         TEXT,
    education_stage_status TEXT,
    age_status             TEXT,
    gender_status          TEXT,
    income_status          TEXT,
    category_status        TEXT,
    rule_version           TEXT,
    rule_json              TEXT NOT NULL,   -- full export_dict() of the compiled rule
    compiled_at            TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_rules_level ON scheme_rules (scheme_level, scheme_state_ut, active_status);

CREATE TABLE IF NOT EXISTS seed_meta (
    dataset                TEXT PRIMARY KEY,
    checksum               TEXT,
    row_count              INTEGER,
    loaded_at              TIMESTAMP
);

-- =========================================================== RESULT TABLES
CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id                 TEXT PRIMARY KEY,
    status                 TEXT NOT NULL,   -- QUEUED / RUNNING / SUCCEEDED / FAILED
    started_at             TIMESTAMP,
    finished_at            TIMESTAMP,
    triggered_by           TEXT,
    error                  TEXT,
    results_json           TEXT             -- funnel, quality, stats, coverage, top schemes
);

CREATE TABLE IF NOT EXISTS link_decisions (
    run_id                 TEXT NOT NULL,
    roll_no                TEXT NOT NULL,
    class_passed           TEXT,
    match_method           TEXT,
    candidates_generated   INTEGER,
    best_member_id         TEXT,
    name_sim               DOUBLE PRECISION,
    dob_result             TEXT,
    father_sim             DOUBLE PRECISION,
    mother_sim             DOUBLE PRECISION,
    gender_result          TEXT,
    overall_score          DOUBLE PRECISION,
    second_member_id       TEXT,
    second_best_score      DOUBLE PRECISION,
    margin                 DOUBLE PRECISION,
    g7_status              TEXT,
    scenario               TEXT,
    classification         TEXT,
    matrix_action          TEXT,
    final_action           TEXT,
    linkage_band           TEXT,
    flag_reason            TEXT,
    linked_member_id       TEXT,
    outreach_status        TEXT,
    gt_true_member_id      TEXT,
    gt_outcome             TEXT,
    detail_json            TEXT,            -- the full decision row (same keys as linkage_decisions.csv)
    PRIMARY KEY (run_id, roll_no)
);
CREATE INDEX IF NOT EXISTS ix_ld_scenario ON link_decisions (run_id, scenario);
CREATE INDEX IF NOT EXISTS ix_ld_band ON link_decisions (run_id, linkage_band);

CREATE TABLE IF NOT EXISTS student_eligibility (
    run_id                 TEXT NOT NULL,
    student_id             TEXT NOT NULL,   -- CBSE roll no
    member_id              TEXT,
    class_passed           TEXT,
    total_checked          INTEGER,
    eligible_count         INTEGER,
    eligible_scheme_ids    TEXT,
    outreach_status        TEXT,
    detail_json            TEXT,
    PRIMARY KEY (run_id, student_id)
);

CREATE TABLE IF NOT EXISTS eligibility_results (
    run_id                 TEXT NOT NULL,
    student_id             TEXT NOT NULL,
    scheme_id              TEXT NOT NULL,
    domicile_result        TEXT,
    education_stage_result TEXT,
    social_category_result TEXT,
    gender_result          TEXT,
    income_result          TEXT,
    age_result             TEXT,
    final_result           TEXT,
    failure_reason         TEXT,
    PRIMARY KEY (run_id, student_id, scheme_id)
);
CREATE INDEX IF NOT EXISTS ix_er_result ON eligibility_results (run_id, final_result);

CREATE TABLE IF NOT EXISTS outreach_queue (
    run_id                 TEXT NOT NULL,
    roll_no                TEXT NOT NULL,
    outreach_status        TEXT NOT NULL,   -- QUEUE_FOR_OUTREACH / QUEUE_FOR_DISCOVERY_OUTREACH
    message_type           TEXT,
    template_name          TEXT,
    mobile                 TEXT,
    sendable               TEXT,
    eligible_scheme_count  INTEGER,
    detail_json            TEXT,
    PRIMARY KEY (run_id, roll_no, outreach_status)
);
CREATE INDEX IF NOT EXISTS ix_oq_status ON outreach_queue (run_id, outreach_status);
