# MoSJE Product 1 – Scholarship Intelligence platform (DB + API + dashboard)

Deployable version of the MoSJE Product 1 prototype: **record linkage** of CBSE 2025-26 pass-outs to
Rajasthan Jan Aadhaar family members (Record Linkage Rules V3.0) and the **scholarship eligibility
engine** against the 547-row Scholarship Master (Eligibility Rule V3.0).

> **Synthetic data only.** Every person, ID and mobile number in `data/` is fictional. Real Jan Aadhaar
> or CBSE data must never be loaded into this deployment. Production belongs on NIC / MeghRaj (see
> `HOSTING_GUIDE.md`, step 11). Your own **anonymised** files can be uploaded: see `UPLOAD_GUIDE.md`
> and `templates/DATA_DICTIONARY.md`.

![architecture](docs/architecture.png)

## Architecture
`dashboard (Streamlit) → API (FastAPI) → Postgres`

* **db/**: SQL migrations (`db/migrations/001_init.sql`), an idempotent seed loader (`db/seed.py`), and the
  repository layer (`db/repository.py`) that holds every query. The code uses SQLAlchemy 2 + psycopg 3.
* **api/**: FastAPI service. The pipeline runs **inside the API process** in a background thread. It reads
  inputs from the database through the repository, runs the unchanged `mosje/` engine and writes the result
  tables.
* **mosje/**: the prototype engine, copied as-is. It adds `scenarios.py` (scenario-wise outcome table) and a
  `compute()` function in `pipeline.py` that does no file IO. The linkage and eligibility rules are unchanged.
* **dashboard/**: Streamlit app. It reads everything from the API (`API_BASE_URL` + `API_KEY`) and has these tabs:
  Funnel, Linkage decisions, Match quality, Eligibility & schemes, Outreach queues, Student drill-down,
  Scenarios, Compiled rules, Admin (seed and run buttons, **Upload datasets**), **Match Outcomes** and **36-Scenario Matrix**
  (reporting view of the earlier 36-row matrix; V3.0 still decides every link).

### Tables
| Group | Tables |
|---|---|
| Inputs | `jan_aadhaar_members` (with normalised `dob_iso` and `gender_norm` blocking keys), `cbse_results`, `ground_truth` (synthetic evaluation only), `scheme_master` (raw xlsx rows as JSON), `scheme_rules` (compiled rules), `seed_meta`, `dataset_sources` (synthetic / uploaded, file name, rows, load time) |
| Results | `pipeline_runs`, `link_decisions`, `student_eligibility`, `eligibility_results` (the full student × scheme audit), `outreach_queue` |

## API (all endpoints except `/health` and `/docs` need header `X-API-Key: $API_KEY`)
| Method | Path | What it does |
|---|---|---|
| GET | `/health` | Liveness, DB type, seeded yes/no, latest run |
| POST | `/admin/seed?force=` | Create tables and load the synthetic CSVs + master (idempotent; replaces uploaded data) |
| POST | `/datasets/cbse/upload?run_pipeline=` | Upload a CBSE file (.csv / .csv.gz / .xlsx, multipart field `file`): validate, then replace `cbse_results` in one transaction. 422 lists missing/extra columns and up to 10 bad rows |
| POST | `/datasets/jan-aadhaar/upload?run_pipeline=` | Same for `jan_aadhaar_members` |
| GET | `/datasets/status` | Source (synthetic / uploaded / cleared), file, rows and load time of CBSE, Jan Aadhaar and ground truth |
| GET | `/admin/status` | Row counts and recent runs |
| GET | `/cbse/students?class=X\|XII&year=2025-26&district=&page=&page_size=` | Paginated CBSE records |
| GET | `/cbse/students/{roll_no}` | One CBSE record |
| GET | `/jan-aadhaar/candidates?dob=&gender=&district=` | Server-side blocking query |
| GET | `/jan-aadhaar/members/{member_id}` | One member |
| GET | `/schemes?level=&state=&active=&q=` | Compiled scheme rules |
| POST | `/pipeline/run?wait=` | Run linkage + eligibility + outreach and store the results |
| GET | `/pipeline/runs`, `/pipeline/runs/{id}` | Run status |
| GET | `/results/funnel` | Funnel, match quality, eligibility stats |
| GET | `/results/scenarios` | 56 matrix rows + EXACT + NO_CANDIDATE + DEFAULT with TP/FP/FN/TN and G7 counts |
| GET | `/results/match-outcomes` | The six headline outcomes (true matches found, false matches, missed matches, precision, recall, FPR) with formulas and plain-English definitions |
| GET | `/results/scenarios-36` | Reporting view: the earlier 36-row matrix (original columns verbatim) with records classified by V3.0 field scores, ground-truth counts, V3.0 mapping, unreachable rows, action-difference notes |
| GET | `/results/decisions?band=&scenario=` | Linkage decisions (paginated) |
| GET | `/results/coverage`, `/results/top-schemes`, `/results/eligibility-summary` | Other result tables |
| GET | `/student/{id}` | CBSE record + decision + best Jan Aadhaar candidate |
| GET | `/student/{id}/eligible-schemes?include_failed=` | Eligible schemes (and optionally the full audit) |
| GET | `/outreach/queue?type=eligible\|discovery` | Outreach queues |

Interactive docs: `/docs` (click **Authorize** and paste the API key).

## Run locally
**With Docker:**
```bash
cp .env.example .env    # set API_KEY
docker compose up --build
# dashboard http://localhost:8501 · API docs http://localhost:8000/docs
```

**Without Docker** (you need Postgres, or leave DATABASE_URL unset to use a local SQLite file):
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://mosje:mosje@localhost:5432/mosje API_KEY=dev-key AUTO_SEED=true AUTO_RUN_PIPELINE=true
.venv/bin/uvicorn api.main:app --port 8000 &
API_BASE_URL=http://localhost:8000 API_KEY=dev-key .venv/bin/streamlit run dashboard/app.py
```
Seed or run from the command line with `python -m db.seed [--force]`. `python -m db.migrate` applies the
migrations only.

## Tests
```bash
.venv/bin/python -m pytest -q                                                    # SQLite
TEST_DATABASE_URL=postgresql://mosje:mosje@localhost:5432/mosje_test .venv/bin/python -m pytest -q   # Postgres (wipes that DB)
API_BASE_URL=http://localhost:8000 API_KEY=dev-key .venv/bin/python tools/parity_check.py ../mosje_prototype/output
```
`docs/test_results.txt` and `docs/parity_report.txt` hold the results from the build machine.

## Deploy to Render
Read **HOSTING_GUIDE.md** (or `HOSTING_GUIDE.docx`). In short: push the repo to GitHub, then in Render go to
New → Blueprint and pick the repo. `render.yaml` creates one free Postgres database, the API and the
dashboard, plus a shared, generated `API_KEY`.

## Environment variables
| Variable | Used by | Meaning |
|---|---|---|
| `DATABASE_URL` | API | Postgres URL (`postgres://…` is accepted). If unset, a local SQLite file is used |
| `API_KEY` | API, dashboard | Shared secret sent in `X-API-Key` |
| `API_BASE_URL` | dashboard | Public URL of the API. On Render, `API_HOST` is used if this is unset |
| `AUTO_SEED`, `AUTO_RUN_PIPELINE` | API | On start-up: load the synthetic data **only if the CBSE and Jan Aadhaar tables are empty** (uploaded data survives restarts), and run once if there are no results |
| `MAX_UPLOAD_ROWS` | API | Largest accepted upload (default 1,000,000 rows) |
| `PIPELINE_MEMORY_LIMIT_MB` | API | Refuse a run whose estimated memory is above this (default 450 on Render, off elsewhere; 0 = off) |
| `KEEP_OLD_RESULTS` | API | `false` (default) replaces the previous run's rows to keep the DB small |
| `PIPELINE_SENSITIVITY` | API | `true` also runs the non-spec sensitivity analysis |
