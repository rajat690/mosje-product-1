import pytest
from mosje.normalize import l1_dob, l1_gender, l1_text, l2_name, soundex, first_name


@pytest.mark.parametrize("raw,expected", [
    ("AARAV SHARMA", "aarav sharma"), ("Aarav  Sharma", "aarav sharma"), ("  Aarav Sharma ", "aarav sharma"),
    ("Mohd. Imran Khan", "mohd imran khan"), ("R.K. Sharma", "r k sharma"),
])
def test_level1_text(raw, expected):
    assert l1_text(raw) == expected


@pytest.mark.parametrize("raw", ["15-07-2010", "15/07/2010", "15 Jul 2010", "2010-07-15"])
def test_level1_dob(raw):
    assert l1_dob(raw) == "2010-07-15"


def test_level1_dob_unparseable():
    assert l1_dob("31-31-2010") is None
    assert l1_dob("") is None


@pytest.mark.parametrize("raw,expected", [("M", "male"), ("Male", "male"), ("MALE", "male"),
                                          ("F", "female"), ("Female", "female")])
def test_level1_gender(raw, expected):
    assert l1_gender(raw) == expected


@pytest.mark.parametrize("raw", ["Mohd Imran Khan", "Md Imran Khan", "Mohd. Imran Khan", "Mohammad Imran Khan",
                                 "Mohammed Imran Khan"])
def test_level2_abbreviation(raw):
    assert l2_name(raw) == "mohammad imran khan"


def test_level2_does_not_touch_other_tokens():
    assert l2_name("Poonam Devi") == "poonam devi"
    assert l2_name("Rajesh K Sharma") == "rajesh k sharma"   # initials are NOT expanded


def test_soundex():
    assert soundex("Robert") == "R163"
    assert soundex("Sharma") == soundex("Sarma") == "S650"


def test_first_name():
    assert first_name("KUMARI PRIYA") == "Priya"
    assert first_name("Mohd. Imran Khan") == "Mohd"
