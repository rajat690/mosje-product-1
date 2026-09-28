import itertools
import random

import pytest

from mosje.matrix import (AUTO_LINK, AUTO_LINK_FLAG, DO_NOT_LINK, DO_NOT_LINK_DISCOVERY, SCENARIOS,
                          classify, field_band, is_reachable, overall_band)


def test_56_rows():
    assert len(SCENARIOS) == 56
    assert [s.id for s in SCENARIOS] == list(range(1, 57))


def test_band_edges():
    assert field_band(90.0) == "H" and field_band(89.99) == "M"
    assert field_band(80.0) == "M" and field_band(79.99) == "L"
    assert overall_band(90) == "O90" and overall_band(89.99) == "O80"
    assert overall_band(70) == "O70" and overall_band(69.99) == "OLT70"


@pytest.mark.parametrize("args,scenario,action", [
    ((100, 100, True, 100, 100, True), 1, AUTO_LINK),
    ((98.91, 95.65, True, 100, 100, True), 1, AUTO_LINK),
    ((95.0, 95, True, 95, 85, True), 2, AUTO_LINK),
    ((95.0, 95, True, 85, 95, True), 3, AUTO_LINK),
    ((91.0, 100, True, 100, 55, True), 4, AUTO_LINK_FLAG),
    ((91.0, 100, True, 55, 100, True), 5, AUTO_LINK_FLAG),
    ((92.0, 95, True, 85, 85, True), 6, AUTO_LINK_FLAG),     # V3.0 change: scenario 6 is Auto-link+flag
    ((90.5, 100, True, 75, 75, True), 7, DO_NOT_LINK),
    ((95.0, 85, True, 100, 100, True), 8, DO_NOT_LINK),
    ((92.0, 75, True, 100, 100, True), 12, DO_NOT_LINK),
    ((88.0, 85, True, 85, 85, True), 31, DO_NOT_LINK_DISCOVERY),
    ((85.0, 70, True, 100, 100, True), 32, DO_NOT_LINK_DISCOVERY),
    ((75.0, 70, True, 70, 70, True), 54, DO_NOT_LINK_DISCOVERY),
    ((70.0, 100, False, 100, 100, True), 55, DO_NOT_LINK_DISCOVERY),
    ((60.0, 50, True, 30, 40, True), 56, DO_NOT_LINK),
    ((0.0, 0, False, 0, 0, False), 56, DO_NOT_LINK),
])
def test_classify(args, scenario, action):
    r = classify(*args)
    assert r.scenario_id == scenario
    assert r.action == action


def test_default_rule_discovery_and_no_outreach():
    # 80-89.99, name >=90, DOB exact, father >=90, mother <80 : not listed -> default
    r = classify(88.0, 100, True, 100, 50, True)
    assert r.scenario_id is None and r.action == DO_NOT_LINK_DISCOVERY
    # >=90 with gender mismatch: not listed -> Do not link
    r = classify(95.0, 100, True, 100, 100, False)
    assert r.scenario_id is None and r.action == DO_NOT_LINK


def test_rows_do_not_overlap():
    rng = random.Random(1)
    for _ in range(20000):
        vals = dict(overall=rng.uniform(0, 100), name=rng.uniform(0, 100), father=rng.uniform(0, 100),
                    mother=rng.uniform(0, 100), dob=rng.random() < 0.7, gender=rng.random() < 0.9)
        from mosje.matrix import _m
        ob, nb = overall_band(vals["overall"]), field_band(vals["name"])
        fb, mb = field_band(vals["father"]), field_band(vals["mother"])
        db = "EXACT" if vals["dob"] else "MISMATCH"
        gb = "EXACT" if vals["gender"] else "MISMATCH"
        hits = [s.id for s in SCENARIOS if s.overall == ob and _m(s.name, nb) and _m(s.dob, db)
                and _m(s.father, fb) and _m(s.mother, mb) and _m(s.gender, gb)]
        assert len(hits) <= 1, hits


def test_action_groups():
    for s in SCENARIOS:
        if s.id <= 3:
            assert s.action == AUTO_LINK
        elif s.id <= 6:
            assert s.action == AUTO_LINK_FLAG
        elif s.id <= 26 or s.id == 56:
            assert s.action == DO_NOT_LINK
        else:
            assert s.action == DO_NOT_LINK_DISCOVERY


def test_reachability_facts():
    # With DOB weight 30, a DOB mismatch caps the overall score at 70 -> rows 18-26 unreachable
    unreachable = {s.id for s in SCENARIOS if not is_reachable(s)}
    assert set(range(18, 27)) <= unreachable
    assert {1, 2, 3, 4, 5, 6, 55, 56} & unreachable == set()
