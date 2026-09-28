"""MoSJE Product 1 platform dashboard. Reads EVERYTHING through the API (never touches the DB).

Env vars: API_BASE_URL (e.g. https://mosje-api.onrender.com) and API_KEY.
Run locally:  streamlit run dashboard/app.py
"""
import time

import altair as alt
import pandas as pd
import streamlit as st

from api_client import ApiError, MosjeApi, candidate_base_urls
from match_outcomes_view import render_match_outcomes
from scenarios36_view import render_scenarios36
from scenarios_view import render_scenarios

st.set_page_config(page_title="MoSJE Scholarship Intelligence", layout="wide")
COLORS = alt.Scale(domain=["Auto-link", "Auto-link+flag", "Do not link + Discovery outreach", "Do not link"],
                   range=["#70AD47", "#FFC000", "#ED7D31", "#C00000"])


@st.cache_resource
def api():
    return MosjeApi()


@st.cache_data(ttl=300, show_spinner="Loading results from the API …")
def load(run_key: str):
    a = api()
    fun = a.get("/results/funnel")
    dec = pd.DataFrame(a.get_all("/results/decisions"))
    summ = pd.DataFrame(a.get("/results/eligibility-summary")["rows"])
    queue = pd.DataFrame(a.get_all("/outreach/queue"))
    cov = pd.DataFrame(a.get("/results/coverage")["rows"])
    top = pd.DataFrame(a.get("/results/top-schemes")["rows"])
    rules = pd.DataFrame(a.get_all("/schemes", page_size=1000))
    scn = pd.DataFrame(a.get("/results/scenarios")["rows"])
    mo = a.get("/results/match-outcomes")
    s36 = a.get("/results/scenarios-36")["rows"]
    return fun, dec, summ, queue, cov, top, rules, scn, mo, s36


st.title("MoSJE Product 1 · Scholarship Intelligence & Outreach Platform")

try:
    health = api().get("/health")
except Exception as e:  # noqa: BLE001
    st.error(f"Cannot reach the API. Tried: {', '.join(candidate_base_urls())}. "
             f"If the API is on Render's free plan it may be waking up (about 1 minute) – reload this page. "
             f"Otherwise set API_BASE_URL on this dashboard service to the API's public URL. ({e})")
    st.stop()


def admin_panel(expanded=True):
    with st.expander("Admin: database & pipeline", expanded=expanded):
        st.write(f"API: `{api().base_url}` · database: **{health.get('database')}** · "
                 f"seeded: **{health.get('seeded')}** · startup: {health.get('startup')}")
        if health.get("startup_error"):
            st.error(health["startup_error"])
        c1, c2, c3 = st.columns(3)
        if c1.button("1 · Load (seed) the database"):
            try:
                with st.spinner("Seeding …"):
                    st.success(api().post("/admin/seed"))
            except ApiError as e:
                st.error(str(e))
        if c2.button("2 · Run the pipeline"):
            try:
                r = api().post("/pipeline/run")
                st.info(f"Started run {r['run_id']} – this takes about 10 s locally, 1–3 min on the free plan.")
                for _ in range(120):
                    time.sleep(3)
                    s = api().get(f"/pipeline/runs/{r['run_id']}")
                    if s["status"] in ("SUCCEEDED", "FAILED"):
                        break
                (st.success if s["status"] == "SUCCEEDED" else st.error)(f"Run {s['run_id']}: {s['status']} "
                                                                         f"{s.get('error') or ''}")
                st.cache_data.clear()
            except ApiError as e:
                st.error(str(e))
        if c3.button("Refresh results"):
            st.cache_data.clear()
            st.rerun()
        try:
            stt = api().get("/admin/status")
            st.dataframe(pd.DataFrame([stt["counts"]]), hide_index=True)
            if stt["runs"]:
                st.dataframe(pd.DataFrame(stt["runs"]).rename(columns={"started_at": "started_at (UTC)", "finished_at": "finished_at (UTC)"}), hide_index=True, width="stretch")
        except ApiError as e:
            st.error(f"{e} – check that API_KEY on the dashboard equals API_KEY on the API.")


latest = health.get("latest_run") or {}
try:
    fun, dec, summ, queue, cov, top, rules, scn, mo, s36 = load(str(latest.get("run_id")))
except ApiError as e:
    st.warning(f"No results yet ({e}). Use the buttons below: first **Load the database**, then **Run the pipeline**.")
    admin_panel(True)
    st.stop()

funnel = pd.DataFrame(fun["funnel"])
fval = dict(zip(funnel.Stage, funnel.Count))
quality = pd.DataFrame(fun["quality"])
ov = quality.iloc[0]
es = fun["eligibility_stats"]
st.caption(f"SYNTHETIC data · Linkage Rules {fun['rule_version']} + Eligibility Rule {fun['rule_version']} · "
           f"Eligibility_As_Of_Date {fun['eligibility_as_of_date']} · run {fun['run_id']} · via API {api().base_url}")

k = st.columns(7)
k[0].metric("CBSE records", f"{int(fval['CBSE records received']):,}")
k[1].metric("Linked", f"{int(fval['Eligibility-checked (linked students)']):,}",
            f"{float(fval['Match rate (linked / received)']):.1%} match rate")
k[2].metric("Precision", f"{ov.Precision:.3f}" if pd.notna(ov.Precision) else "n/a")
k[3].metric("Recall", f"{ov.Recall:.3f}" if pd.notna(ov.Recall) else "n/a")
k[4].metric("QUEUE_FOR_OUTREACH", f"{int(fval['QUEUE_FOR_OUTREACH']):,}")
k[5].metric("DISCOVERY queue", f"{int(fval['QUEUE_FOR_DISCOVERY_OUTREACH']):,}")
k[6].metric("Eligible schemes / student", f"{es['eligible_mean']}",
            f"median {es['eligible_median']}, max {es['eligible_max']}", delta_color="off")

tabs = st.tabs(["Funnel", "Linkage decisions", "Match quality", "Eligibility & schemes", "Outreach queues",
                "Student drill-down", "Scenarios", "Compiled rules", "Admin", "Match Outcomes", "36-Scenario Matrix"])

with tabs[0]:
    stages = ["CBSE records received", "Exact matches (unique, all 5 fields after L1)",
              "Fuzzy-evaluated (>=1 blocking candidate)", "Auto-linked (Scenarios 1-3)",
              "Auto-linked + flag (Scenarios 4-6)", "Probable - Discovery (overall 70-89.99)",
              "Not linked, no outreach", "Eligibility-checked (linked students)", "Eligible for >=1 scheme",
              "QUEUE_FOR_OUTREACH", "QUEUE_FOR_DISCOVERY_OUTREACH", "NO_OUTREACH"]
    fd = funnel[funnel.Stage.isin(stages)].copy()
    fd["order"] = fd.Stage.map({s: i for i, s in enumerate(stages)})
    fd["Count"] = fd.Count.astype(float)
    chart = alt.Chart(fd).mark_bar(color="#2F5597").encode(
        x=alt.X("Count:Q"), y=alt.Y("Stage:N", sort=alt.SortField("order"), title=None, axis=alt.Axis(labelLimit=380)),
        tooltip=["Stage", "Count", "Note"]).properties(height=420)
    st.altair_chart(chart + chart.mark_text(align="left", dx=3).encode(text=alt.Text("Count:Q", format=",.0f")),
                    width="stretch")
    st.dataframe(funnel.astype({"Count": str}), width="stretch", hide_index=True)

with tabs[1]:
    c1, c2 = st.columns(2)
    ac = dec.Final_Action.value_counts().rename_axis("Action").reset_index(name="Records")
    c1.subheader("Final action")
    c1.altair_chart(alt.Chart(ac).mark_bar().encode(x="Records:Q", y=alt.Y("Action:N", sort="-x", title=None),
                    color=alt.Color("Action:N", scale=COLORS, legend=None), tooltip=["Action", "Records"]),
                    width="stretch")
    c2.subheader("Match method & G7")
    c2.dataframe(dec.groupby(["Match_Method", "G7"]).size().reset_index(name="Records"), hide_index=True,
                 width="stretch")
    st.subheader("Scenario coverage (records per matrix row)")
    cv = cov[pd.to_numeric(cov.Records) > 0].astype({"Scenario": str})
    st.altair_chart(alt.Chart(cv).mark_bar().encode(
        x=alt.X("Scenario:N", sort=None), y="Records:Q", color=alt.Color("Action:N", scale=COLORS),
        tooltip=["Scenario", "Classification", "Action", "Records", "Decision_Correct_vs_GT"]), width="stretch")
    st.dataframe(cov.astype({"Scenario": str}), hide_index=True, width="stretch")

with tabs[2]:
    st.subheader("Match quality vs ground truth (spec section 8)")
    st.caption("TP = linked to true member · FP = linked to wrong member or student not in Jan Aadhaar · "
               "FN = true member exists but not linked · FPR = FP/(FP+TN)")
    st.dataframe(quality, hide_index=True, width="stretch")
    nq = quality[quality.Segment.str.startswith("Noise:") & quality.Recall.notna()]
    st.altair_chart(alt.Chart(nq).mark_bar(color="#548235").encode(
        x=alt.X("Recall:Q", scale=alt.Scale(domain=[0, 1])), y=alt.Y("Segment:N", sort="-x", title=None),
        tooltip=["Segment", "Records", "True_Matches_TP", "Missed_Matches_FN", "Recall"]), width="stretch")

with tabs[3]:
    c1, c2 = st.columns([2, 1])
    c1.subheader("Top eligible schemes (linked students)")
    c1.altair_chart(alt.Chart(top.head(20)).mark_bar(color="#7030A0").encode(
        x="Eligible_Students:Q", y=alt.Y("Scheme_Name:N", sort="-x", title=None, axis=alt.Axis(labelLimit=420)),
        tooltip=["Scheme_ID", "Scheme_Name", "Level", "Eligible_Students"]), width="stretch")
    c2.subheader("Eligible schemes per student")
    if len(summ):
        c2.altair_chart(alt.Chart(summ).mark_bar().encode(
            x=alt.X("Eligible_Scheme_Count:Q", bin=alt.Bin(step=1)), y="count()", color="Class_Passed:N"),
            width="stretch")
    c2.write(f"Mean **{es['eligible_mean']}**, median **{es['eligible_median']}**, max **{es['eligible_max']}**, "
             f"min **{es['eligible_min']}** of {es['candidate_schemes_per_student']} candidate schemes.")
    c2.dataframe(pd.Series(es["failure_first_check"]).rename_axis("First failing check").reset_index(name="Pairs"),
                 hide_index=True)
    st.dataframe(top, hide_index=True, width="stretch")

with tabs[4]:
    q1 = queue[queue.Outreach_Status == "QUEUE_FOR_OUTREACH"] if len(queue) else queue
    q2 = queue[queue.Outreach_Status == "QUEUE_FOR_DISCOVERY_OUTREACH"] if len(queue) else queue
    a, b = st.columns(2)
    a.metric("QUEUE_FOR_OUTREACH (eligible shortlist)", f"{len(q1):,}",
             f"{(q1.Sendable == 'YES').sum() if len(q1) else 0:,} sendable", delta_color="off")
    b.metric("QUEUE_FOR_DISCOVERY_OUTREACH", f"{len(q2):,}",
             f"{(q2.Sendable == 'YES').sum() if len(q2) else 0:,} sendable", delta_color="off")
    t1, t2 = st.tabs(["Eligible shortlist", "Discovery"])
    with t1:
        st.warning("Eligible-shortlist template is a PROTOTYPE DRAFT (not in the Linkage doc).")
        if len(q1):
            st.dataframe(q1[["Roll_No", "Candidate_Name", "Class_Passed", "Mobile", "Contact_Source", "Sendable",
                             "Eligible_Scheme_Count", "Top_Schemes_In_Message"]], hide_index=True, width="stretch")
            st.text(q1.iloc[0].Message_EN)
    with t2:
        if len(q2):
            st.dataframe(q2[["Roll_No", "Candidate_Name", "Class_Passed", "Mobile", "Sendable",
                             "Best_Candidate_Score", "Scenario"]], hide_index=True, width="stretch")
            x, y = st.columns(2)
            x.text(q2.iloc[0].Message_EN)
            y.text(q2.iloc[0].Message_HI)

with tabs[5]:
    st.subheader("Single-student drill-down")
    band = st.radio("Filter", ["All", "MATCHED", "PROBABLE", "NOT MATCHED", "G7 fail"], horizontal=True, index=1)
    pool = dec if band == "All" else dec[dec.G7 == "FAIL"] if band == "G7 fail" else dec[dec.Linkage_Band == band]
    labels = (pool.Roll_No.astype(str) + " · " + pool.CBSE_Name + " · " + pool.Final_Action).tolist()
    pick = st.selectbox("CBSE roll number", labels, index=0 if labels else None)
    if pick:
        roll = pick.split(" · ")[0]
        info = api().get(f"/student/{roll}")
        d = info["decision"]
        c1, c2 = st.columns(2)
        c1.markdown("**CBSE record**")
        c1.dataframe(pd.Series(info["cbse"], dtype=str).rename("value"), width="stretch")
        c2.markdown(f"**Best Jan Aadhaar candidate** ({d.get('Best_Member_ID') or 'none'})")
        if info["best_candidate"]:
            c2.dataframe(pd.Series(info["best_candidate"], dtype=str).rename("value"), width="stretch")
        st.markdown("**Scores & decision**")
        keys = ["Match_Method", "Candidates_Generated", "Name_Sim_%", "DOB", "Father_Sim_%", "Mother_Sim_%", "Gender",
                "Overall_Score", "Second_Best_Score", "Margin", "G7", "Scenario", "Classification", "Final_Action",
                "Flag_Reason", "Outreach_Status", "GT_True_Member_ID", "GT_Outcome", "GT_Noise"]
        st.dataframe(pd.DataFrame([{k2: str(d.get(k2, "")) for k2 in keys}]), hide_index=True, width="stretch")
        if d["Linkage_Band"] == "MATCHED":
            el = api().get(f"/student/{roll}/eligible-schemes", include_failed="true")
            s = el["summary"]
            st.success(f"{s['Eligible_Scheme_Count']} eligible of {s['Total_Candidate_Schemes_Checked']} candidate "
                       f"schemes · category {s['Social_Category']} · income {s['Annual_Family_Income']} · "
                       f"stage {s['Student_Education_Stage']}")
            sch = pd.DataFrame(el["schemes"])
            st.markdown("**Eligible schemes (all six checks PASS)**")
            st.dataframe(sch[sch.final_result == "ELIGIBLE"][["scheme_id", "Scheme_Name", "Scheme_Level",
                                                             "Categories_Allowed", "Income_Raw", "Application_Portal",
                                                             "Benefits"]], hide_index=True, width="stretch")
            st.markdown("**Not eligible (first failing check)**")
            st.dataframe(sch[sch.final_result != "ELIGIBLE"][["scheme_id", "Scheme_Name", "failure_reason"]],
                         hide_index=True, width="stretch")
        elif d["Linkage_Band"] == "PROBABLE":
            st.warning("PROBABLE band: not linked, eligibility engine NOT run. Queued for the Discovery template.")
        else:
            st.error("Not linked - no outreach.")

with tabs[6]:
    render_scenarios(scn)

with tabs[7]:
    st.subheader("Compiled scheme rules")
    st.dataframe(rules, hide_index=True, width="stretch")

with tabs[8]:
    admin_panel(True)

with tabs[9]:
    render_match_outcomes(mo["outcomes"], mo.get("counts"))

with tabs[10]:
    render_scenarios36(s36)
