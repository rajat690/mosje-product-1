"""Worked examples from Record Linkage Rules V3.0, section 3."""
from difflib import SequenceMatcher

import pytest

from mosje.linkage import direct_ratio, name_similarity, token_sort_ratio, weighted_score
from mosje.normalize import l2_name


def _mt(a, b):
    sm = SequenceMatcher(None, a, b)
    return sum(bl.size for bl in sm.get_matching_blocks()), len(a) + len(b)


@pytest.mark.parametrize("ja,m,t,sim,conf", [
    ("Aarav Sarma", 11, 23, 95.65, 98.91),
    ("Karav Sarma", 10, 23, 86.96, 96.74),
    ("Karav Sharma", 11, 24, 91.67, 97.92),
    ("Arav Sharma", 11, 23, 95.65, 98.91),
    ("Aarav Sharma", 12, 24, 100.00, 100.00),
])
def test_name_formula_table(ja, m, t, sim, conf):
    a, b = l2_name("Aarav Sharma"), l2_name(ja)
    assert _mt(a, b) == (m, t)
    s = name_similarity(a, b)
    assert round(s, 2) == sim
    assert weighted_score(s, True, 100, 100, True) == conf


@pytest.mark.parametrize("field,cbse,ja,direct,ts,used", [
    ("Candidate", "Kumari Priya", "Priya Kumari", 50.00, 100.00, 100.00),
    ("Candidate", "Sharma Aarav", "Aarav Sarma", 43.48, 95.65, 95.65),
    ("Father", "Sharma Rajesh", "Rajesh Sharma", 46.15, 100.00, 100.00),
    ("Mother", "Devi Sunita", "Sunita Devi", 54.55, 100.00, 100.00),
])
def test_token_sort_worked_example(field, cbse, ja, direct, ts, used):
    a, b = l2_name(cbse), l2_name(ja)
    assert round(direct_ratio(a, b), 2) == direct
    assert round(token_sort_ratio(a, b), 2) == ts
    assert round(name_similarity(a, b), 2) == used


def test_kumari_priya_confidence_and_without_token_sort():
    a, b = l2_name("Kumari Priya"), l2_name("Priya Kumari")
    assert weighted_score(name_similarity(a, b), True, 100, 100, True) == 100.00
    # without token-sort the score would be 87.50 (PROBABLE band)
    assert weighted_score(direct_ratio(a, b), True, 100, 100, True) == 87.50


def test_sharma_aarav_reversed_and_misspelt():
    a, b = l2_name("Sharma Aarav"), l2_name("Aarav Sarma")
    assert weighted_score(name_similarity(a, b), True, 100, 100, True) == 98.91


def test_token_sort_never_reduces():
    for a, b in [("rajesh k sharma", "rajesh kumar sharma"), ("poonam devi", "punam devi")]:
        assert name_similarity(a, b) >= direct_ratio(a, b)


def test_missing_value_scores_zero():
    assert name_similarity("", "sunita devi") == 0.0


def test_g7_example_scores():
    assert weighted_score(96, True, 95, 94, True) == 96.80
    assert weighted_score(94, True, 92, 91, True) == 95.10
