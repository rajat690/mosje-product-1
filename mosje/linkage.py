"""Record linkage engine (Record Linkage Rules V3.0).

Flow per CBSE record:
    Level-1 normalisation -> exact match on all five fields -> (if none) blocking passes ->
    dedupe candidates -> weighted fuzzy score per candidate -> matrix row for the best
    candidate -> Guardrail G7 (top-candidate margin) for scenarios 1-6 -> action.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, asdict
from difflib import SequenceMatcher
from typing import Iterable, Optional

from . import config
from .matrix import (AUTO_LINK, AUTO_LINK_FLAG, DO_NOT_LINK, DO_NOT_LINK_DISCOVERY,
                     LINK_ACTIONS, SCENARIO_BY_ID, classify)
from .normalize import l1_dob, l1_gender, l1_text, l2_name, phonetic_keys, token_sort

MATCHED, PROBABLE, NOT_MATCHED = "MATCHED", "PROBABLE", "NOT MATCHED"


# ------------------------------------------------------------------ similarity
def direct_ratio(a: str, b: str) -> float:
    """(2M / T) x 100 using difflib.SequenceMatcher.ratio()."""
    return SequenceMatcher(None, a, b).ratio() * 100.0


def token_sort_ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, token_sort(a), token_sort(b)).ratio() * 100.0


def name_similarity(a: str, b: str) -> float:
    """MAX(direct ratio, token-sort ratio). Missing value on either side -> 0."""
    if not a or not b:
        return 0.0
    return max(direct_ratio(a, b), token_sort_ratio(a, b))


def weighted_score(name_sim: float, dob_exact: bool, father_sim: float,
                   mother_sim: float, gender_exact: bool) -> float:
    w = config.WEIGHTS
    s = (w["dob"] * (1.0 if dob_exact else 0.0)
         + w["name"] * name_sim / 100.0
         + w["father"] * father_sim / 100.0
         + w["mother"] * mother_sim / 100.0
         + w["gender"] * (1.0 if gender_exact else 0.0))
    return round(s, 2)


# ------------------------------------------------------------------ records
@dataclass
class NormRecord:
    rid: str
    name_l1: str
    name_l2: str
    dob: Optional[str]
    gender: Optional[str]
    father_l1: str
    father_l2: str
    mother_l1: str
    mother_l2: str

    @property
    def exact_key(self):
        return (self.name_l1, self.dob, self.gender, self.father_l1, self.mother_l1)


def normalize_record(rid, name, dob, gender, father, mother) -> NormRecord:
    return NormRecord(
        rid=str(rid), name_l1=l1_text(name), name_l2=l2_name(name), dob=l1_dob(dob),
        gender=l1_gender(gender), father_l1=l1_text(father), father_l2=l2_name(father),
        mother_l1=l1_text(mother), mother_l2=l2_name(mother))


@dataclass
class CandidateScore:
    member_id: str
    name_direct: float
    name_token_sort: float
    name_sim: float
    dob_exact: bool
    father_sim: float
    mother_sim: float
    gender_exact: bool
    overall: float
    passes: str = ""


def score_pair(c: NormRecord, j: NormRecord, passes: str = "") -> CandidateScore:
    nd = direct_ratio(c.name_l2, j.name_l2) if c.name_l2 and j.name_l2 else 0.0
    nt = token_sort_ratio(c.name_l2, j.name_l2) if c.name_l2 and j.name_l2 else 0.0
    ns = max(nd, nt)
    fs = name_similarity(c.father_l2, j.father_l2)
    ms = name_similarity(c.mother_l2, j.mother_l2)
    de = c.dob is not None and c.dob == j.dob
    ge = c.gender is not None and c.gender == j.gender
    return CandidateScore(j.rid, round(nd, 2), round(nt, 2), round(ns, 2), de,
                          round(fs, 2), round(ms, 2), ge,
                          weighted_score(ns, de, fs, ms, ge), passes)


# ------------------------------------------------------------------ index
class JanAadhaarIndex:
    """Exact-match hash index + the four blocking passes from spec section 4."""

    def __init__(self, records: Iterable[NormRecord], extra_parent_pass: bool = None):
        self.records: dict[str, NormRecord] = {}
        self.exact = defaultdict(list)
        self.blocks = defaultdict(set)
        self.extra = config.EXTRA_BLOCKING_PARENTS_WITHOUT_DOB if extra_parent_pass is None else extra_parent_pass
        for r in records:
            self.records[r.rid] = r
            self.exact[r.exact_key].append(r.rid)
            for key in self._keys(r):
                self.blocks[key].add(r.rid)

    def _keys(self, r: NormRecord):
        if r.dob:
            if r.gender:
                yield ("P1", r.dob, r.gender)                         # DOB + Gender
            for k in phonetic_keys(r.name_l2):
                yield ("P2", r.dob, k)                                # DOB + name phonetic
            for k in phonetic_keys(r.father_l2):
                yield ("P3", r.dob, k)                                # Father + DOB
            for k in phonetic_keys(r.mother_l2):
                yield ("P4", r.dob, k)                                # Mother + DOB
        if self.extra and r.father_l2 and r.mother_l2:                # NOT in spec (sensitivity only)
            yield ("PX", token_sort(r.father_l2), token_sort(r.mother_l2))

    def candidates(self, c: NormRecord) -> dict[str, list[str]]:
        found = defaultdict(list)
        for key in self._keys(c):
            for rid in self.blocks.get(key, ()):
                if key[0] not in found[rid]:
                    found[rid].append(key[0])
        return found


# ------------------------------------------------------------------ decision
@dataclass
class LinkageDecision:
    roll_no: str
    match_method: str                 # EXACT / FUZZY / NO_CANDIDATE
    candidate_count: int
    best_member_id: Optional[str] = None
    best_passes: str = ""
    name_direct: Optional[float] = None
    name_token_sort: Optional[float] = None
    name_sim: Optional[float] = None
    dob_result: Optional[str] = None
    father_sim: Optional[float] = None
    mother_sim: Optional[float] = None
    gender_result: Optional[str] = None
    overall_score: float = 0.0
    second_member_id: Optional[str] = None
    second_score: Optional[float] = None
    margin: Optional[float] = None
    g7_status: str = "NOT_APPLICABLE"
    scenario: Optional[int] = None
    scenario_label: str = ""
    classification: str = ""
    matrix_action: str = ""
    action: str = ""
    linkage_band: str = NOT_MATCHED
    flag_reason: str = ""
    linked_member_id: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _apply_matrix(d: LinkageDecision, best: CandidateScore, n_candidates: int,
                  second: Optional[CandidateScore]):
    d.best_member_id = best.member_id
    d.best_passes = best.passes
    d.name_direct, d.name_token_sort, d.name_sim = best.name_direct, best.name_token_sort, best.name_sim
    d.dob_result = "Exact" if best.dob_exact else "Mismatch"
    d.father_sim, d.mother_sim = best.father_sim, best.mother_sim
    d.gender_result = "Exact" if best.gender_exact else "Mismatch"
    d.overall_score = best.overall
    mr = classify(best.overall, best.name_sim, best.dob_exact, best.father_sim,
                  best.mother_sim, best.gender_exact)
    d.scenario = mr.scenario_id
    d.scenario_label = str(mr.scenario_id) if mr.scenario_id else "DEFAULT"
    d.classification = mr.classification
    d.matrix_action = mr.action
    action = mr.action
    reasons = []
    if second is not None:
        d.second_member_id = second.member_id
        d.second_score = second.overall
        d.margin = round(best.overall - second.overall, 2)
    if action in LINK_ACTIONS:
        if n_candidates >= 2 and second is not None:
            if d.margin >= config.G7_MIN_MARGIN:
                d.g7_status = "PASS"
            else:
                d.g7_status = "FAIL"
                action = DO_NOT_LINK
                reasons.append(f"G7 fail: margin {d.margin:.2f} < {config.G7_MIN_MARGIN:g} "
                               f"(2nd candidate {second.member_id} = {second.overall:.2f})")
        else:
            d.g7_status = "NOT_APPLICABLE"
    if action == AUTO_LINK_FLAG:
        reasons.append(f"Parent discrepancy: father {best.father_sim:.2f}%, mother {best.mother_sim:.2f}%")
    if mr.scenario_id is None:
        reasons.append("Default rule: combination not listed in matrix")
    if action in (DO_NOT_LINK, DO_NOT_LINK_DISCOVERY) and not reasons:
        reasons.append(mr.classification)
    d.action = action
    d.flag_reason = "; ".join(reasons)
    if action in LINK_ACTIONS:
        d.linkage_band = MATCHED
        d.linked_member_id = best.member_id
    elif action == DO_NOT_LINK_DISCOVERY:
        d.linkage_band = PROBABLE
    else:
        d.linkage_band = NOT_MATCHED


def link_record(c: NormRecord, index: JanAadhaarIndex) -> LinkageDecision:
    # ---- Step 1: exact match after Level-1 normalisation
    if c.dob and c.gender and c.name_l1:
        exact_ids = index.exact.get(c.exact_key, [])
        if len(exact_ids) == 1:
            best = CandidateScore(exact_ids[0], 100.0, 100.0, 100.0, True, 100.0, 100.0, True, 100.0, "EXACT")
            d = LinkageDecision(c.rid, "EXACT", 1)
            _apply_matrix(d, best, 1, None)
            d.flag_reason = "Exact match on all five fields after Level-1 normalisation"
            return d
        if len(exact_ids) > 1:
            ids = sorted(exact_ids)
            best = CandidateScore(ids[0], 100.0, 100.0, 100.0, True, 100.0, 100.0, True, 100.0, "EXACT")
            second = CandidateScore(ids[1], 100.0, 100.0, 100.0, True, 100.0, 100.0, True, 100.0, "EXACT")
            d = LinkageDecision(c.rid, "EXACT", len(ids))
            _apply_matrix(d, best, len(ids), second)
            return d
    # ---- Step 2: blocking + fuzzy scoring
    cands = index.candidates(c)
    if not cands:
        d = LinkageDecision(c.rid, "NO_CANDIDATE", 0)
        s = SCENARIO_BY_ID[56]
        d.scenario, d.scenario_label, d.classification = 56, "56", s.classification
        d.matrix_action = d.action = DO_NOT_LINK
        d.flag_reason = "No candidate generated by blocking passes (overall score 0 < 70)"
        return d
    scored = [score_pair(c, index.records[mid], "+".join(p)) for mid, p in cands.items()]
    return decide(c.rid, scored)


def decide(roll_no: str, scored: list[CandidateScore]) -> LinkageDecision:
    """Apply matrix + G7 to a list of (deduplicated) scored candidates."""
    scored = sorted(scored, key=lambda s: (-s.overall, s.member_id))
    d = LinkageDecision(roll_no, "FUZZY", len(scored))
    _apply_matrix(d, scored[0], len(scored), scored[1] if len(scored) > 1 else None)
    return d
