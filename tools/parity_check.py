"""Compare the platform's results (fetched through the API) with the prototype's CSV outputs.

    python tools/parity_check.py /path/to/mosje_prototype/output   [API_BASE_URL/API_KEY from env]

Checks, row by row: every linkage decision (all columns), every student eligibility summary, every
outreach queue item, the scenario table, and the headline funnel. Prints a PASS/FAIL report.
"""
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "dashboard"))
from api_client import MosjeApi  # noqa: E402


def norm(v):
    if v is None:
        return ""
    s = str(v)
    try:
        f = float(s)
        return f"{f:.4f}"
    except ValueError:
        return s


def read(p):
    with open(p, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def compare(name, proto_rows, api_rows, key, ignore=()):
    P = {r[key]: r for r in proto_rows}
    A = {str(r[key]): r for r in api_rows}
    bad = []
    if set(P) != set(A):
        bad.append(f"key sets differ: only prototype {len(set(P) - set(A))}, only platform {len(set(A) - set(P))}")
    for k in set(P) & set(A):
        for col, pv in P[k].items():
            if col in ignore:
                continue
            if norm(pv) != norm(A[k].get(col)):
                bad.append(f"{k}.{col}: prototype={pv!r} platform={A[k].get(col)!r}")
                break
    print(f"{'PASS' if not bad else 'FAIL'}  {name}: {len(P)} prototype rows vs {len(A)} platform rows"
          + ("" if not bad else f", {len(bad)} mismatches e.g. {bad[:3]}"))
    return not bad


def main(out_dir):
    out = Path(out_dir)
    api = MosjeApi()
    ok = True
    ok &= compare("linkage decisions", read(out / "linkage_decisions.csv"), api.get_all("/results/decisions"), "Roll_No")
    ok &= compare("student eligibility summary", read(out / "student_eligibility_summary.csv"),
                  api.get("/results/eligibility-summary")["rows"], "Student_ID")
    pq = read(out / "outreach_queue.csv")
    aq = api.get_all("/outreach/queue")
    ok &= compare("outreach queue", pq, aq, "Roll_No")
    ok &= compare("scenario outcomes", read(out / "scenario_outcomes.csv"),
                  api.get("/results/scenarios")["rows"], "Scenario")
    ok &= compare("compiled scheme rules", read(out / "compiled_scheme_rules.csv"),
                  api.get_all("/schemes", page_size=1000), "Scheme_ID")
    pf = {r["Stage"]: r["Count"] for r in read(out / "funnel.csv")}
    af = {r["Stage"]: r["Count"] for r in api.get("/results/funnel")["funnel"]}
    same = all(norm(pf[k]) == norm(af.get(k)) for k in pf)
    print(f"{'PASS' if same else 'FAIL'}  funnel: {len(pf)} stages")
    ok &= same
    print("OVERALL:", "PASS – platform results identical to the prototype" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PROTOTYPE_OUTPUT", "../mosje_prototype/output")))
