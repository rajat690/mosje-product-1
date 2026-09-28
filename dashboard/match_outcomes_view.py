"""'Match Outcomes' dashboard tab: the six headline linkage outcomes with plain-English definitions.

Shared by the local prototype dashboard (reads output/match_outcomes.csv) and the platform dashboard
(reads GET /results/match-outcomes). Input: list of dicts / DataFrame with the columns produced by
mosje.match_outcomes.match_outcomes(): Key, Outcome, Value, Display, Formula, Definition, Better_When.
"""
import pandas as pd
import streamlit as st

ORDER = ["true_matches", "false_matches", "missed_matches", "precision", "recall", "false_positive_rate"]
SHORT = {"true_matches": "Correct links",
         "false_matches": "Wrong links",
         "missed_matches": "In JA, not linked",
         "precision": "Correct / all links",
         "recall": "Found / could be found",
         "false_positive_rate": "Wrong / not in JA"}


def outcomes_frame(outcomes) -> pd.DataFrame:
    """Normalise to one row per outcome in the fixed order. Raises if an outcome is missing."""
    df = pd.DataFrame(outcomes).copy()
    df["Key"] = df["Key"].astype(str)
    missing = [k for k in ORDER if k not in set(df["Key"])]
    if missing:
        raise ValueError(f"match outcomes missing: {missing}")
    df = df.set_index("Key").loc[ORDER].reset_index()
    df["Display"] = df["Display"].fillna("n/a").astype(str)
    return df


def explanatory_table(df: pd.DataFrame) -> pd.DataFrame:
    return df.rename(columns={"Display": "Result", "Formula": "How it is calculated",
                              "Definition": "What it means", "Better_When": "Better when"})[
        ["Outcome", "Result", "How it is calculated", "What it means", "Better when"]]


def render_match_outcomes(outcomes, counts: dict | None = None):
    df = outcomes_frame(outcomes)
    st.subheader("Match outcomes vs ground truth")
    st.caption("How well the record linkage did, measured against the synthetic ground truth (one CBSE record = "
               "one decision). These are the same numbers as the Match quality tab, overall row.")
    cols = st.columns(6)
    for col, (_, r) in zip(cols, df.iterrows()):
        col.metric(r.Outcome, r.Display, SHORT[r.Key], delta_color="off", delta_arrow="off", border=True,
                   help=f"{r.Formula}. {r.Definition}")
    st.markdown("**What each outcome means**")
    st.dataframe(explanatory_table(df), hide_index=True, width="stretch",
                 column_config={"What it means": st.column_config.TextColumn(width="large")})
    if counts:
        st.caption(f"Underlying counts: {counts.get('records', 0):,} CBSE records · "
                   f"{counts.get('records_with_true_ja_member', 0):,} really in Jan Aadhaar · "
                   f"TP {counts.get('TP', 0):,} · FP {counts.get('FP', 0):,} · FN {counts.get('FN', 0):,} · "
                   f"TN {counts.get('TN', 0):,} (TN = not in Jan Aadhaar and correctly not linked). "
                   "A link to the wrong member counts once as FP and once as FN.")
