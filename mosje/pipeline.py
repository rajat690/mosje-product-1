"""End-to-end pipeline: synthetic data -> rules compiler -> linkage -> eligibility -> outreach -> reports."""
from __future__ import annotations

import csv
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

from . import config, synthetic
from .eligibility import EligibilityEngine, build_profile
from .linkage import (MATCHED, NOT_MATCHED, PROBABLE, JanAadhaarIndex, link_record,
                      normalize_record)
from .matrix import (AUTO_LINK, AUTO_LINK_FLAG, BAND_LABEL, DO_NOT_LINK, DO_NOT_LINK_DISCOVERY,
                     SCENARIOS, is_reachable, reachable_score_range)
from .match_outcomes import match_outcomes, overall_row
from .metrics import outcome, summarize
from .outreach import discovery_item, eligible_item
from .rules_compiler import compile_master
from .scenarios36 import export_rows as s36_export, scenarios36, summary as s36_summary
from .scenarios import EXPORT_COLS as SCN_COLS, scenario_outcomes, summary as scenario_summary


def read_csv(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict]):
    if not rows:
        path.write_text("")
        return
    keys = list(rows[0].keys())
    for r in rows[1:]:
        for k in r:
            if k not in keys:
                keys.append(k)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)


def run_linkage(cbse, ja, extra_parent_pass=None):
    ja_norm = [normalize_record(m["member_id"], m["nameEng"], m["dob"], m["gender"],
                                m["fatherNameEng"], m["motherNameEng"]) for m in ja]
    index = JanAadhaarIndex(ja_norm, extra_parent_pass=extra_parent_pass)
    norm, decisions = [], []
    for c in cbse:
        n = normalize_record(c["roll_no"], c["candidate_name"], c["dob"], c["gender"],
                             c["father_name"], c["mother_name"])
        norm.append(n)
        decisions.append(link_record(n, index))
    return norm, decisions


def quality_tables(decisions, truth_by_roll):
    rows = []
    for d in decisions:
        t = truth_by_roll[d.roll_no]
        o = outcome(d.linked_member_id, t["true_member_id"])
        o.update(true_mid=t["true_member_id"], probable=d.linkage_band == PROBABLE,
                 noise=t["noise_types"], lookalike=t["has_lookalike_or_twin"], cls=t["class_passed"])
        rows.append(o)
    table = [summarize(rows, "OVERALL")]
    table.append(summarize([r for r in rows if r["true_mid"]], "Students present in Jan Aadhaar"))
    table.append(summarize([r for r in rows if not r["true_mid"]], "Students NOT in Jan Aadhaar"))
    for cls in ("X", "XII"):
        table.append(summarize([r for r in rows if r["cls"] == cls], f"Class {cls}"))
    table.append(summarize([r for r in rows if r["lookalike"] == "Y"], "Has twin / near-lookalike in JA"))
    tags = sorted({tg for r in rows for tg in r["noise"].split(";")})
    for tg in tags:
        table.append(summarize([r for r in rows if tg in r["noise"].split(";")], f"Noise: {tg}"))
    return rows, table


def run(regenerate: bool = False, verbose: bool = True) -> dict:
    """Prototype entry point: read data/ CSVs + the master xlsx, compute, write output/."""
    t0 = time.time()
    log = print if verbose else (lambda *a, **k: None)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    ja_path = config.DATA_DIR / "jan_aadhaar_members.csv"
    if regenerate or not ja_path.exists():
        log("Generating synthetic data ...", synthetic.generate())
    ja = read_csv(ja_path)
    cbse = read_csv(config.DATA_DIR / "cbse_passed_2025_26.csv")
    truth = read_csv(config.DATA_DIR / "ground_truth.csv")
    log(f"Loaded {len(ja):,} Jan Aadhaar members, {len(cbse):,} CBSE records")
    rules = compile_master()
    log(f"Compiled {len(rules)} scheme rows ({sum(r.Active_Status == 'ACTIVE' for r in rules)} active)")
    c = compute(ja, cbse, truth, rules, log=log, t0=t0)
    write_outputs(c, config.OUTPUT_DIR, log=log, t0=t0)
    return c["results"]


def compute(ja: list[dict], cbse: list[dict], truth: list[dict], rules: list, log=None,
            t0: float | None = None, sensitivity: bool = True) -> dict:
    """Pure computation (no file IO): linkage -> eligibility -> outreach -> summary tables.

    Used by the prototype (CSV in / files out) and by the platform API (DB in / DB out).
    ja / cbse / truth are lists of dicts with the CSV column names (values as strings);
    truth may be empty (no ground truth, e.g. real data) - GT columns are then blank.
    """
    t0 = t0 or time.time()
    log = log or (lambda *a, **k: None)
    truth_by_roll = {t["roll_no"]: t for t in truth}
    for c in cbse:                       # records without ground truth (real data) get blank GT fields
        truth_by_roll.setdefault(c["roll_no"], {"roll_no": c["roll_no"], "true_member_id": "",
                                                 "noise_types": "", "has_lookalike_or_twin": "",
                                                 "class_passed": c.get("class_passed", "")})
    ja_by_mid = {m["member_id"]: m for m in ja}
    cbse_by_roll = {c["roll_no"]: c for c in cbse}
    rules_by_id = {r.Scheme_ID: r for r in rules}

    # ---- linkage
    norm, decisions = run_linkage(cbse, ja)
    log(f"Linkage done in {time.time() - t0:.1f}s")
    q_rows, quality = quality_tables(decisions, truth_by_roll)

    # ---- eligibility (MATCHED only)
    engine = EligibilityEngine(rules)
    ts = datetime.now().isoformat(timespec="seconds")
    summaries, audits, profiles = [], [], {}
    for d in decisions:
        if d.linkage_band != MATCHED:
            continue
        c = cbse_by_roll[d.roll_no]
        m = ja_by_mid[d.linked_member_id]
        p = build_profile(d.roll_no, m, c["class_passed"])
        profiles[d.roll_no] = p
        s, a = engine.evaluate_student(p, ts)
        s.update({"Candidate_Name": c["candidate_name"], "Class_Passed": c["class_passed"],
                  "Social_Category": p.Social_Category, "Gender": p.Gender,
                  "Annual_Family_Income": p.Annual_Family_Income, "Calculated_Age": p.Calculated_Age,
                  "Domicile_State_UT": p.Domicile_State_UT, "District": m["district"],
                  "Student_Education_Stage": "; ".join(sorted(p.Student_Education_Stage or []))})
        summaries.append(s)
        audits.extend(a)
    log(f"Eligibility: {len(summaries):,} students, {len(audits):,} student-scheme pairs")

    # ---- outreach
    summ_by_roll = {s["Student_ID"]: s for s in summaries}

    def specificity(sid):
        r = rules_by_id[sid]
        return sum(st == "PARSED" for st in (r.Education_Stage_Status, r.Category_Status,
                                             r.Gender_Status, r.Income_Status, r.Age_Status))
    queue = []
    outreach_status = {}
    for d in decisions:
        c = cbse_by_roll[d.roll_no]
        if d.linkage_band == MATCHED:
            s = summ_by_roll[d.roll_no]
            if s["Eligible_Scheme_Count"] >= 1:
                ids = s["Eligible_Scheme_IDs"].split("; ")
                ids.sort(key=lambda i: (-specificity(i), rules_by_id[i].Scheme_Level != "State/UT",
                                        rules_by_id[i].Scheme_Name))
                top = [rules_by_id[i].Scheme_Name for i in ids[:3]]
                queue.append(eligible_item(c, ja_by_mid[d.linked_member_id], s, top))
                outreach_status[d.roll_no] = "QUEUE_FOR_OUTREACH"
            else:
                outreach_status[d.roll_no] = "NO_OUTREACH"
        elif d.linkage_band == PROBABLE:
            queue.append(discovery_item(c, d.to_dict()))
            outreach_status[d.roll_no] = "QUEUE_FOR_DISCOVERY_OUTREACH"
        else:
            outreach_status[d.roll_no] = "NO_OUTREACH"

    # ---- decision table
    dec_rows = []
    for d, n, qr in zip(decisions, norm, q_rows):
        c = cbse_by_roll[d.roll_no]
        best = ja_by_mid.get(d.best_member_id) if d.best_member_id else None
        t = truth_by_roll[d.roll_no]
        dd = d.to_dict()
        row = {
            "Roll_No": d.roll_no, "Class": c["class_passed"], "CBSE_Name": c["candidate_name"],
            "CBSE_DOB_raw": c["dob"], "CBSE_DOB_norm": n.dob, "CBSE_Gender_raw": c["gender"],
            "CBSE_Father": c["father_name"], "CBSE_Mother": c["mother_name"],
            "Match_Method": d.match_method, "Candidates_Generated": d.candidate_count,
            "Best_Member_ID": d.best_member_id or "", "Best_JA_Name": best["nameEng"] if best else "",
            "Best_JA_DOB": best["dob"] if best else "", "Best_JA_Father": best["fatherNameEng"] if best else "",
            "Best_JA_Mother": best["motherNameEng"] if best else "", "Blocking_Passes": d.best_passes,
            "Name_Direct_%": dd["name_direct"], "Name_TokenSort_%": dd["name_token_sort"],
            "Name_Sim_%": dd["name_sim"], "DOB": dd["dob_result"] or "", "Father_Sim_%": dd["father_sim"],
            "Mother_Sim_%": dd["mother_sim"], "Gender": dd["gender_result"] or "",
            "Overall_Score": d.overall_score, "Second_Member_ID": d.second_member_id or "",
            "Second_Best_Score": d.second_score, "Margin": d.margin, "G7": d.g7_status,
            "Scenario": d.scenario_label, "Classification": d.classification,
            "Matrix_Action": d.matrix_action, "Final_Action": d.action, "Linkage_Band": d.linkage_band,
            "Flag_Reason": d.flag_reason, "Linked_Member_ID": d.linked_member_id or "",
            "Outreach_Status": outreach_status[d.roll_no],
            "GT_True_Member_ID": t["true_member_id"], "GT_Noise": t["noise_types"],
            "GT_Twin_or_Lookalike": t["has_lookalike_or_twin"],
            "GT_Correct": "YES" if (qr["TP"] or qr["TN"]) else "NO",
            "GT_Outcome": "TP" if qr["TP"] else "FP-wrong member" if qr["wrong_member"] else "FP" if qr["FP"]
                          else "FN" if qr["FN"] else "TN",
        }
        dec_rows.append(row)

    # ---- funnel
    act = Counter(d.action for d in decisions)
    band = Counter(d.linkage_band for d in decisions)
    n_norm = sum(1 for n in norm if n.dob and n.gender and n.name_l1)
    n_exact = sum(1 for d in decisions if d.match_method == "EXACT" and d.linkage_band == MATCHED)
    n_exact_multi = sum(1 for d in decisions if d.match_method == "EXACT" and d.linkage_band != MATCHED)
    n_fuzzy = sum(1 for d in decisions if d.match_method == "FUZZY")
    n_nocand = sum(1 for d in decisions if d.match_method == "NO_CANDIDATE")
    g7_fail = sum(1 for d in decisions if d.g7_status == "FAIL")
    linked = band[MATCHED]
    elig_counts = [s["Eligible_Scheme_Count"] for s in summaries]
    n_elig = sum(1 for x in elig_counts if x >= 1)
    osc = Counter(outreach_status.values())
    sendable = Counter((q["Outreach_Status"], q["Sendable"].startswith("YES")) for q in queue)
    N = len(cbse)
    funnel = [
        ("CBSE records received", N, ""),
        ("Normalized (name, DOB and gender parsed)", n_norm, "Level-1 normalisation"),
        ("Exact matches (unique, all 5 fields after L1)", n_exact, "Auto-link, Scenario 1, no fuzzy step"),
        ("Exact-key hits on >1 JA member (not unique)", n_exact_multi, "Do not link (G7 margin 0)"),
        ("Fuzzy-evaluated (>=1 blocking candidate)", n_fuzzy, "Weighted score + matrix"),
        ("No blocking candidate", n_nocand, "Do not link, Scenario 56"),
        ("Auto-linked (Scenarios 1-3)", act[AUTO_LINK], "incl. exact matches"),
        ("Auto-linked + flag (Scenarios 4-6)", act[AUTO_LINK_FLAG], "Parent discrepancy"),
        ("G7 margin failures (would have linked)", g7_fail, "Do not link, no outreach"),
        ("Probable - Discovery (overall 70-89.99)", band[PROBABLE], "Not linked"),
        ("Not linked, no outreach", band[NOT_MATCHED], "<70, >=90 guardrail fail, or G7 fail"),
        ("Match rate (linked / received)", round(linked / N, 4), f"{linked:,} linked"),
        ("Eligibility-checked (linked students)", len(summaries), ""),
        ("Eligible for >=1 scheme", n_elig, ""),
        ("QUEUE_FOR_OUTREACH", osc["QUEUE_FOR_OUTREACH"],
         f"{sendable[('QUEUE_FOR_OUTREACH', True)]:,} with a valid mobile"),
        ("QUEUE_FOR_DISCOVERY_OUTREACH", osc["QUEUE_FOR_DISCOVERY_OUTREACH"],
         f"{sendable[('QUEUE_FOR_DISCOVERY_OUTREACH', True)]:,} with a valid CBSE mobile (others not sent)"),
        ("NO_OUTREACH", osc["NO_OUTREACH"],
         f"{sum(1 for s in summaries if s['Eligible_Scheme_Count'] == 0):,} linked-but-0-eligible + "
         f"{band[NOT_MATCHED]:,} not linked"),
    ]
    funnel_rows = [{"Stage": a, "Count": b, "Note": c} for a, b, c in funnel]

    # ---- scenario coverage
    sc_count = Counter(d.scenario_label for d in decisions)
    sc_correct = Counter(r["Scenario"] for r in dec_rows if r["GT_Correct"] == "YES")
    sc_tm = Counter(r["Scenario"] for r in dec_rows if r["GT_True_Member_ID"]
                    and r["Best_Member_ID"] == r["GT_True_Member_ID"])
    cov = []
    for s in SCENARIOS:
        lo, hi = reachable_score_range(s)
        cov.append({"Scenario": s.id, "Overall": BAND_LABEL[s.overall], "Name": BAND_LABEL[s.name],
                    "DOB": BAND_LABEL[s.dob], "Father": BAND_LABEL[s.father], "Mother": BAND_LABEL[s.mother],
                    "Gender": BAND_LABEL[s.gender], "Classification": s.classification, "Action": s.action,
                    "Achievable_Score_Range": f"{lo:.2f}–{hi:.2f}",
                    "Mathematically_Reachable": "Yes" if is_reachable(s) else "NO",
                    "Records": sc_count.get(str(s.id), 0),
                    "Best_Candidate_Is_True_Member": sc_tm.get(str(s.id), 0),
                    "Decision_Correct_vs_GT": sc_correct.get(str(s.id), 0)})
    cov.append({"Scenario": "DEFAULT", "Overall": "any", "Classification": "Combination not listed",
                "Action": "Do not link (+ Discovery if 70–89.99)", "Mathematically_Reachable": "Yes",
                "Records": sc_count.get("DEFAULT", 0),
                "Best_Candidate_Is_True_Member": sc_tm.get("DEFAULT", 0),
                "Decision_Correct_vs_GT": sc_correct.get("DEFAULT", 0)})

    # ---- scenario-wise outcomes (all 56 rows + exact path + no candidate + default)
    scn_rows = scenario_outcomes(dec_rows)
    scn_export = [{k: r[k] for k in SCN_COLS} for r in scn_rows]
    scn_summary = scenario_summary(scn_rows)
    # ---- reporting view: the earlier 36-row matrix (does not affect any link)
    s36_rows = scenarios36(dec_rows)
    s36_export_rows = s36_export(s36_rows)

    # ---- eligibility stats
    scheme_elig = Counter()
    for s in summaries:
        for sid in filter(None, s["Eligible_Scheme_IDs"].split("; ")):
            scheme_elig[sid] += 1
    top_schemes = [{"Scheme_ID": sid, "Scheme_Name": rules_by_id[sid].Scheme_Name,
                    "Level": rules_by_id[sid].Scheme_Level, "State_UT": rules_by_id[sid].Scheme_State_UT,
                    "Eligible_Students": n,
                    "Specific_Conditions_Parsed": specificity(sid)} for sid, n in scheme_elig.most_common()]
    fail_reason = Counter()
    for a in audits:
        if a["Final_Result"] != "ELIGIBLE":
            fail_reason[a["Failure_Reason"].split(":")[0]] += 1
    stats = {
        "eligible_mean": round(mean(elig_counts), 2) if elig_counts else 0,
        "eligible_median": median(elig_counts) if elig_counts else 0,
        "eligible_max": max(elig_counts) if elig_counts else 0,
        "eligible_min": min(elig_counts) if elig_counts else 0,
        "candidate_schemes_per_student": summaries[0]["Total_Candidate_Schemes_Checked"] if summaries else 0,
        "eligible_by_class": {cls: round(mean([s["Eligible_Scheme_Count"] for s in summaries
                                               if s["Class_Passed"] == cls] or [0]), 2) for cls in ("X", "XII")},
        "failure_first_check": dict(fail_reason.most_common()),
        "audit_pairs": len(audits),
    }
    rule_stats = {
        "total_rows": len(rules),
        "active": sum(r.Active_Status == "ACTIVE" for r in rules),
        "excluded": sum(r.Active_Status == "EXCLUDED" for r in rules),
        "compile_status": dict(Counter(r.Compile_Status for r in rules)),
        "central_plus_rajasthan_active": len(engine.CENTRAL_SCHEMES) + len(engine.STATE_UT_SCHEMES.get("rajasthan", [])),
        "field_status": {f: dict(Counter(getattr(r, f) for r in rules if r.Active_Status == "ACTIVE"))
                         for f in ("Education_Stage_Status", "Age_Status", "Gender_Status",
                                   "Income_Status", "Category_Status")},
    }

    # ---- optional sensitivity run (NOT the spec): extra parent-only blocking pass
    if sensitivity:
        _, dec_x = run_linkage(cbse, ja, extra_parent_pass=True)
        _, q_x = quality_tables(dec_x, truth_by_roll)
        sens = q_x[0]
        sens["Segment"] = "SENSITIVITY (not spec): + Father+Mother blocking pass without DOB"
        sensitivity_bands = dict(Counter(d.linkage_band for d in dec_x))
    else:
        sens, sensitivity_bands = {}, {}

    results = {
        "generated_at": ts, "rule_version": config.RULE_VERSION,
        "eligibility_as_of_date": config.ELIGIBILITY_AS_OF_DATE.isoformat(),
        "counts": {"jan_aadhaar_members": len(ja), "cbse_records": N,
                   "cbse_in_ja": sum(1 for t in truth if t["true_member_id"])},
        "funnel": funnel_rows, "quality": quality, "eligibility_stats": stats, "rule_stats": rule_stats,
        "action_counts": dict(act), "band_counts": dict(band), "outreach_counts": dict(osc),
        "sensitivity": sens, "sensitivity_bands": sensitivity_bands,
        "scenario_summary": scn_summary,
        "match_outcomes": match_outcomes(overall_row(quality)),
        "scenarios36_summary": s36_summary(s36_rows),
        "runtime_seconds": round(time.time() - t0, 1),
    }
    return {"results": results, "decisions": dec_rows, "summaries": summaries, "audits": audits,
            "queue": queue, "rules": rules, "quality": quality, "coverage": cov, "funnel": funnel_rows,
            "top_schemes": top_schemes, "scenario_outcomes": scn_export,
            "match_outcomes": match_outcomes(overall_row(quality)), "scenarios36": s36_export_rows}


def write_outputs(c: dict, out: Path, log=None, t0: float | None = None):
    t0 = t0 or time.time()
    log = log or (lambda *a, **k: None)
    results = c["results"]
    rules = c["rules"]
    write_csv(out / "linkage_decisions.csv", c["decisions"])
    write_csv(out / "student_eligibility_summary.csv", c["summaries"])
    write_csv(out / "eligibility_audit_full.csv", c["audits"])
    write_csv(out / "outreach_queue.csv", c["queue"])
    write_csv(out / "compiled_scheme_rules.csv", [r.export_dict() for r in rules])
    write_csv(out / "match_quality.csv", c["quality"])
    write_csv(out / "scenario_coverage.csv", c["coverage"])
    write_csv(out / "funnel.csv", c["funnel"])
    write_csv(out / "top_eligible_schemes.csv", c["top_schemes"])
    write_csv(out / "scenario_outcomes.csv", c["scenario_outcomes"])
    write_csv(out / "match_outcomes.csv", c["match_outcomes"])
    write_csv(out / "scenarios36.csv", c["scenarios36"])
    (out / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    from .report import write_workbook
    write_workbook(out / "MoSJE_Prototype_Results.xlsx", c["funnel"], c["decisions"], c["quality"],
                   c["summaries"], c["audits"], [r.export_dict() for r in rules], c["queue"], c["coverage"],
                   c["top_schemes"], results, scenario_outcomes=c["scenario_outcomes"],
                   match_outcomes=c["match_outcomes"], scenarios36=c["scenarios36"])
    results["runtime_seconds"] = round(time.time() - t0, 1)
    (out / "results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    log(f"Done in {results['runtime_seconds']}s -> {out}")
