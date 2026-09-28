"""'Scenarios' dashboard tab: matching / non-matching students against every matrix scenario.

Shared by the local prototype dashboard (reads output/scenario_outcomes.csv) and the platform
dashboard (reads GET /results/scenarios). Input: DataFrame with the columns of
mosje.scenarios.EXPORT_COLS.
"""
import altair as alt
import pandas as pd
import streamlit as st

ACTIONS = ["Auto-link", "Auto-link+flag", "Do not link", "Do not link + Discovery",
           "Do not link (+ Discovery if 70–89.99)"]
OUTCOME_COLORS = alt.Scale(domain=["TP", "FP", "FN", "TN"], range=["#70AD47", "#C00000", "#ED7D31", "#8FAADC"])
OUTCOME_LABEL = {"TP": "TP – linked, correct", "FP": "FP – linked, wrong person",
                 "FN": "FN – not linked, true match exists", "TN": "TN – not linked, not in JA"}


def render_scenarios(scn: pd.DataFrame):
    st.subheader("Matching / non-matching students by decision-matrix scenario")
    st.caption("All 56 rows of the Record Linkage V3.0 matrix, plus the exact-match path (EXACT), "
               "'no blocking candidate' (NO_CANDIDATE) and the default rule. Ground truth: TP = linked to the "
               "true member · FP = linked to the wrong person · FN = not linked although the student is in "
               "Jan Aadhaar · TN = not linked and genuinely not in Jan Aadhaar. Rows marked **Unreachable** can "
               "never be hit with weights 30/25/20/20/5. Scenario 1 counts fuzzy-path records only.")
    scn = scn.copy()
    for c in ["Records", "Linked", "Not_Linked", "TP", "FP", "FN", "TN", "G7_Blocked"]:
        scn[c] = pd.to_numeric(scn[c], errors="coerce").fillna(0).astype(int)
    tot = scn[["Records", "TP", "FP", "FN", "TN", "G7_Blocked"]].sum()
    k = st.columns(7)
    k[0].metric("CBSE records", f"{tot.Records:,}")
    k[1].metric("Matching (linked)", f"{tot.TP + tot.FP:,}")
    k[2].metric("Non-matching (not linked)", f"{tot.FN + tot.TN:,}")
    k[3].metric("TP / FP", f"{tot.TP:,} / {tot.FP:,}")
    k[4].metric("FN / TN", f"{tot.FN:,} / {tot.TN:,}")
    k[5].metric("G7-blocked", f"{tot.G7_Blocked:,}")
    k[6].metric("Unreachable rows", f"{(scn.Status == 'Unreachable').sum()} of 56")

    c1, c2 = st.columns([3, 1])
    present = [a for a in ACTIONS if a in set(scn.Action)]
    pick = c1.multiselect("Filter by action", present, default=present, key="scn_action")
    show = c2.radio("Rows", ["All", "Hit only", "Unreachable only"], horizontal=False, key="scn_rows")
    view = scn[scn.Action.isin(pick)]
    if show == "Hit only":
        view = view[view.Records > 0]
    elif show == "Unreachable only":
        view = view[view.Status == "Unreachable"]

    chart_df = view[view.Records > 0].melt(id_vars=["Scenario", "Action", "Criteria", "Records"],
                                             value_vars=["TP", "FP", "FN", "TN"], var_name="Outcome",
                                             value_name="Count")
    chart_df = chart_df[chart_df.Count > 0]
    if len(chart_df):
        chart_df["Outcome_Label"] = chart_df.Outcome.map(OUTCOME_LABEL)
        order = list(view[view.Records > 0].Scenario)
        hide_exact = st.checkbox(f"Hide the EXACT row from the chart (it has "
                                 f"{int(scn.loc[scn.Scenario == 'EXACT', 'Records'].sum()):,} records and flattens "
                                 f"the other bars)", value=True, key="scn_hide_exact")
        if hide_exact:
            chart_df = chart_df[chart_df.Scenario != "EXACT"]
            order = [o for o in order if o != "EXACT"]
        y = alt.Y("Count:Q", stack=True, title="CBSE records")
        base = alt.Chart(chart_df)
        bars = base.mark_bar().encode(
            x=alt.X("Scenario:N", sort=order, title="Scenario"), y=y,
            color=alt.Color("Outcome:N", scale=OUTCOME_COLORS, title="Ground truth",
                            legend=alt.Legend(labelExpr="{'TP':'TP – linked, correct','FP':'FP – linked, wrong person',"
                                                        "'FN':'FN – not linked, true match exists',"
                                                        "'TN':'TN – not linked, not in JA'}[datum.label]",
                                              labelLimit=300)),
            order=alt.Order("Outcome:N"),
            tooltip=["Scenario", "Action", "Criteria", "Outcome_Label", "Count", "Records"]).properties(height=380)
        labels = base.transform_aggregate(Total="sum(Count)", groupby=["Scenario"]).mark_text(
            dy=-6, fontSize=11).encode(x=alt.X("Scenario:N", sort=order), y="Total:Q", text=alt.Text("Total:Q", format=","))
        st.altair_chart(bars + labels, width="stretch")
    else:
        st.info("No records in the selected rows.")

    disp = view.copy()
    cols = ["Scenario", "Status", "Action", "Records", "TP", "FP", "FN", "TN", "G7_Blocked", "Criteria",
            "Classification", "Overall", "Name", "DOB", "Father", "Mother", "Gender", "Achievable_Score_Range",
            "Linked", "Not_Linked", "FN_Best_Candidate_Was_True_Member", "Precision"]
    cols = [c for c in cols if c in disp.columns]
    unreach = disp.Status == "Unreachable"
    for c in ["Records", "TP", "FP", "FN", "TN", "G7_Blocked", "Linked", "Not_Linked",
              "FN_Best_Candidate_Was_True_Member"]:
        if c not in disp.columns:
            continue
        disp[c] = pd.to_numeric(disp[c], errors="coerce").astype(float)
        disp.loc[unreach, c] = float("nan")     # shown blank; Status says Unreachable

    def style(row):
        if row.Status == "Unreachable":
            return ["color: #999999; background-color: #F2F2F2"] * len(row)
        return [""] * len(row)
    cnt = [c for c in ["Records", "TP", "FP", "FN", "TN", "G7_Blocked", "Linked", "Not_Linked",
                       "FN_Best_Candidate_Was_True_Member"] if c in cols]
    styled = disp[cols].style.apply(style, axis=1).format(na_rep="—", subset=cnt, precision=0)
    if "Precision" in cols:
        styled = styled.format(na_rep="", subset=["Precision"], precision=3)
    st.dataframe(styled, hide_index=True, width="stretch",
                 height=min(38 + 35 * len(disp), 2200),
                 column_config={"Criteria": st.column_config.TextColumn(width="large"),
                                "Status": st.column_config.TextColumn(width="medium"),
                                "Action": st.column_config.TextColumn(width="medium")})
    st.caption("Click a column header to sort. Counts of Unreachable rows are left blank on purpose "
               "(shown as None, not 0; Status = Unreachable): those band combinations cannot occur with the current weights.")
    st.download_button("Download scenario table (CSV)", scn.to_csv(index=False).encode(), "scenario_outcomes.csv",
                       "text/csv")
