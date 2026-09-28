"""'36-Scenario Matrix' dashboard tab (reporting view only; V3.0 decides every link).

Shared by the local prototype dashboard (reads output/scenarios36.csv) and the platform dashboard
(reads GET /results/scenarios-36). Input: rows with the columns of mosje.scenarios36.EXPORT_COLS.
"""
import pandas as pd
import streamlit as st

ORIGINAL = ["#", "Overall Score", "Candidate Name", "DOB", "Father Name", "Mother Name", "Gender",
            "Classification", "Action"]
COUNTS = ["Records", "True matches (correct link)", "False matches (wrong link)", "Missed matches",
          "Correctly not linked", "G7-blocked"]
ADDED = ["Status"] + COUNTS + ["of which exact path", "V3.0 scenario(s) by conditions", "V3.0 scenario(s) observed",
                              "Action differs from V3.0 (records)", "Note"]


def prepare(rows) -> pd.DataFrame:
    df = pd.DataFrame(rows).copy()
    missing = [c for c in ORIGINAL + ADDED if c not in df.columns]
    if missing:
        raise ValueError(f"36-scenario rows missing columns: {missing}")
    df = df[ORIGINAL + ADDED]
    for c in COUNTS + ["of which exact path", "Action differs from V3.0 (records)"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in ORIGINAL + ["Status", "V3.0 scenario(s) by conditions", "V3.0 scenario(s) observed", "Note"]:
        df[c] = df[c].fillna("").astype(str)
    return df


def display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Count cells of unreachable rows read 'Unreachable' instead of 0."""
    out = df.copy()
    cols = COUNTS + ["of which exact path"]
    out[cols] = out[cols].astype(object)
    out.loc[out.Status == "Unreachable", cols] = "Unreachable"
    return out


GT_COUNTS = ["True matches (correct link)", "False matches (wrong link)", "Missed matches", "Correctly not linked"]


def render_scenarios36(rows, ground_truth_available: bool = True):
    df = prepare(rows)
    st.subheader("Earlier 36-scenario decision matrix, applied to this run's scores")
    st.warning("Reporting view only. The live linkage rules are V3.0 (56-row matrix + G7 margin); they decided "
               "every link counted here. This tab shows where each record would sit in the earlier 36-row matrix.")
    st.caption("Columns # to Action are the original 36-row matrix, verbatim. Each record's V3.0 field scores "
               "(best candidate) are checked against rows 1–36 top to bottom; the first matching row wins. "
               "Exact-path records score 100 on every field and fall into row 1. NO_CANDIDATE = no blocking "
               "candidate (no scores). NOT_LISTED = scores match none of the 36 rows. Unreachable = cannot occur "
               "with weights 30/25/20/20/5. 'Action differs' compares the 36-row action (with the ≥5-point "
               "top-candidate margin rule on rows 1–5) with the action V3.0 actually gave.")
    tot = df[COUNTS].sum()
    gt = ground_truth_available
    if not gt:
        st.info("Match-outcome columns: not available (no ground truth) for uploaded data.")
    k = st.columns(7)
    k[0].metric("Records", f"{tot['Records']:,}")
    k[1].metric("True matches", f"{tot['True matches (correct link)']:,}" if gt else "n/a")
    k[2].metric("False matches", f"{tot['False matches (wrong link)']:,}" if gt else "n/a")
    k[3].metric("Missed matches", f"{tot['Missed matches']:,}" if gt else "n/a")
    k[4].metric("Correctly not linked", f"{tot['Correctly not linked']:,}" if gt else "n/a")
    m = df[df["#"].str.isdigit()]
    k[5].metric("Unreachable rows", f"{(m.Status == 'Unreachable').sum()} of 36")
    k[6].metric("Action differs from V3.0", f"{df['Action differs from V3.0 (records)'].sum():,} records")
    only_hit = st.checkbox("Show only rows with records", value=False, key="s36_only_hit")
    view = df[df.Records > 0] if only_hit else df
    shown = display_frame(view)
    if not gt:
        shown = shown.drop(columns=GT_COUNTS)
    st.dataframe(shown, hide_index=True, width="stretch", height=35 * (len(view) + 1) + 3,
                 column_config={"Note": st.column_config.TextColumn(width="large"),
                                "Classification": st.column_config.TextColumn(width="medium")})
    notes = df[df.Note != ""]
    if len(notes):
        st.markdown("**Where the 36-row action differs from what V3.0 did**")
        for _, r in notes.iterrows():
            st.markdown(f"- Row **{r['#']}**: {r.Note}")
