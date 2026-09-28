"""Admin tab: 'Upload datasets' section. Everything goes through the API (never the database).

POST /datasets/cbse/upload, POST /datasets/jan-aadhaar/upload, GET /datasets/status, POST /pipeline/run.
"""
from __future__ import annotations

import time

import pandas as pd
import streamlit as st

from api_client import ApiError

UPLOADS = [("cbse", "CBSE passed students", "/datasets/cbse/upload", "templates/cbse_template.csv"),
           ("ja", "Jan Aadhaar members", "/datasets/jan-aadhaar/upload", "templates/jan_aadhaar_template.csv")]
SOURCE_LABEL = {"synthetic": "Synthetic (bundled)", "uploaded": "Uploaded by you", "cleared": "Cleared",
                "empty": "Empty", "unknown": "Unknown"}


def status_frame(status: dict) -> pd.DataFrame:
    names = {"cbse_results": "CBSE passed students", "jan_aadhaar_members": "Jan Aadhaar members",
             "ground_truth": "Ground truth (synthetic only)"}
    rows = []
    for key, label in names.items():
        d = (status.get("datasets") or {}).get(key) or {}
        rows.append({"Dataset": label, "Source": SOURCE_LABEL.get(d.get("source"), d.get("source")),
                     "File": d.get("filename") or "", "Rows now": d.get("rows"),
                     "Loaded at (UTC)": str(d.get("loaded_at") or "")[:19].replace("T", " ")})
    return pd.DataFrame(rows)


def validation_summary(payload) -> tuple[list[str], pd.DataFrame | None, list[str]]:
    """Turn the API's 422 detail into (messages, bad-rows table, warnings) for display."""
    if not isinstance(payload, dict):
        return [str(payload)], None, []
    msgs = list(payload.get("errors") or [])
    if payload.get("missing_columns"):
        msgs.append("Missing columns: " + ", ".join(payload["missing_columns"]))
    if payload.get("extra_columns"):
        msgs.append("Extra columns (ignored): " + ", ".join(payload["extra_columns"]))
    for problem, n in (payload.get("problem_counts") or {}).items():
        msgs.append(f"{n:,} × {problem}")
    bad = payload.get("bad_rows_sample") or []
    table = None
    if bad:
        table = pd.DataFrame([{"Line in file": b["row"], "Problems": "; ".join(b["errors"]),
                               **{k: v for k, v in (b.get("values") or {}).items()}} for b in bad])
    return msgs, table, list(payload.get("warnings") or [])


def run_pipeline_and_wait(api) -> dict | None:
    r = api.post("/pipeline/run")
    st.info(f"Started run {r['run_id']}: about 10 s locally, 1–3 min on the free plan (longer for big files).")
    s = {}
    for _ in range(600):
        time.sleep(3)
        s = api.get(f"/pipeline/runs/{r['run_id']}")
        if s["status"] in ("SUCCEEDED", "FAILED"):
            break
    (st.success if s.get("status") == "SUCCEEDED" else st.error)(
        f"Run {s.get('run_id')}: {s.get('status')} {s.get('error') or ''}"
        + (" · press **Refresh results** (top of this panel) to see the new numbers." if s.get("status") == "SUCCEEDED"
           else ""))
    st.cache_data.clear()
    return s


def render_upload_section(api):
    st.markdown("### Upload datasets")
    st.warning("Upload only **anonymised or synthetic** data here. Real government personal data must not be "
               "put on Render or GitHub; it belongs on NIC / MeghRaj.")
    try:
        status = api.get("/datasets/status")
        st.dataframe(status_frame(status), hide_index=True, width="stretch")
        if not status.get("ground_truth_available"):
            st.caption("No ground truth for the current data, so precision, recall and TP/FP/FN are shown as "
                       "'n/a'. Funnel, decisions, eligibility and outreach work as usual.")
        if not status.get("results_ready"):
            st.info("No results for the current data yet: press **Run matching**.")
    except ApiError as e:
        st.error(f"Could not read the dataset status: {e}")
    st.caption("Use the column names in templates/cbse_template.csv and templates/jan_aadhaar_template.csv "
               "(see templates/DATA_DICTIONARY.md). Accepted: .csv (UTF-8), .csv.gz, .xlsx. Each upload REPLACES "
               "that table. Upload both files, then press Run matching.")
    cols = st.columns(2)
    for col, (key, label, path, tpl) in zip(cols, UPLOADS):
        with col:
            f = st.file_uploader(label, type=["csv", "gz", "xlsx"], key=f"up_{key}")
            if f is not None and st.button(f"Upload {label}", key=f"btn_{key}", type="primary"):
                try:
                    with st.spinner(f"Uploading and checking {f.name} …"):
                        r = api.upload(path, f.name, f.getvalue())
                    st.success(f"Loaded {r['rows_loaded']:,} rows from {r['filename']}. "
                               "Old results were removed; press Run matching.")
                    for w in r.get("warnings") or []:
                        st.warning(w)
                    st.cache_data.clear()
                except ApiError as e:
                    if e.status == 422:
                        msgs, table, warns = validation_summary(e.payload)
                        st.error("The file was NOT loaded (nothing changed). Please fix these problems:\n\n" +
                                 "\n".join(f"- {m}" for m in msgs))
                        if table is not None:
                            st.markdown("**First rows with problems** (line numbers as in the file; header = line 1)")
                            st.dataframe(table, hide_index=True, width="stretch")
                        for w in warns:
                            st.warning(w)
                    else:
                        st.error(str(e))
    if st.button("Run matching (linkage + eligibility)", key="run_matching"):
        try:
            run_pipeline_and_wait(api)
        except ApiError as e:
            st.error(str(e))
