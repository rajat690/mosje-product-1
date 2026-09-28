"""Match-quality metrics (Record Linkage Rules V3.0, section 8), computed against ground truth.

Record-level definitions (one CBSE record = one decision):
  TP  linked to the true Jan Aadhaar member
  FP  linked, but to the wrong member OR the student has no Jan Aadhaar record
  FN  student has a Jan Aadhaar record but was not linked to it (not linked, or linked wrongly)
  TN  student has no Jan Aadhaar record and was not linked
  Precision = TP/(TP+FP)   Recall = TP/(TP+FN)   FPR = FP/(FP+TN)
Note: a wrong-member link counts once as FP and once as FN.
"""
from __future__ import annotations


def outcome(linked_mid, true_mid) -> dict:
    linked_mid = linked_mid or ""
    true_mid = true_mid or ""
    tp = bool(linked_mid) and linked_mid == true_mid
    fp = bool(linked_mid) and linked_mid != true_mid
    fn = bool(true_mid) and linked_mid != true_mid
    tn = not true_mid and not linked_mid
    return {"TP": tp, "FP": fp, "FN": fn, "TN": tn, "wrong_member": fp and bool(true_mid)}


def summarize(rows: list[dict], label: str) -> dict:
    """rows need keys TP/FP/FN/TN/wrong_member/probable/true_mid."""
    n = len(rows)
    tp = sum(r["TP"] for r in rows)
    fp = sum(r["FP"] for r in rows)
    fn = sum(r["FN"] for r in rows)
    tn = sum(r["TN"] for r in rows)
    wm = sum(r["wrong_member"] for r in rows)
    pos = sum(1 for r in rows if r["true_mid"])
    prob = sum(1 for r in rows if r["probable"])
    prob_true = sum(1 for r in rows if r["probable"] and r["true_mid"])
    return {
        "Segment": label, "Records": n, "Records_with_true_JA_member": pos,
        "True_Matches_TP": tp, "False_Matches_FP": fp, "of_which_wrong_member": wm,
        "Missed_Matches_FN": fn, "True_Negatives_TN": tn,
        "Precision": round(tp / (tp + fp), 4) if tp + fp else None,
        "Recall": round(tp / (tp + fn), 4) if tp + fn else None,
        "False_Positive_Rate": round(fp / (fp + tn), 4) if fp + tn else None,
        "Routed_to_Discovery": prob, "Discovery_where_true_member_exists": prob_true,
    }
