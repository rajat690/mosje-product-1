"""Normalisation levels from Record Linkage Rules V3.0, section 2.

Level 1 - safe deterministic: case, spaces, punctuation, DOB format, gender coding.
Level 2 - controlled Indian-name normalisation (Mohd./Md./Mohammed -> mohammad), used cautiously.
Level 3 - phonetic keys and fuzzy similarity; these only feed a confidence score / blocking key
          and never overwrite the original data.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Optional

from . import config

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

_DOB_FORMATS = (
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%d %b %Y", "%d %B %Y",
    "%d-%b-%Y", "%Y/%m/%d", "%d %b, %Y",
)

_GENDER_MAP = {
    "m": "male", "male": "male", "boy": "male",
    "f": "female", "female": "female", "girl": "female",
    "t": "transgender", "tg": "transgender", "transgender": "transgender",
    "o": "other", "other": "other",
}


# ---------------------------------------------------------------- Level 1
def l1_text(value: Optional[str]) -> str:
    """Lower-case, punctuation -> space, collapse and trim spaces.

    'Mohd. Imran Khan' -> 'mohd imran khan'; 'R.K. Sharma' -> 'r k sharma'.
    """
    if value is None:
        return ""
    s = str(value).strip().lower()
    s = _PUNCT_RE.sub(" ", s).replace("_", " ")
    return _SPACE_RE.sub(" ", s).strip()


def l1_dob(value) -> Optional[str]:
    """Return ISO yyyy-mm-dd, or None if the value cannot be parsed."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = _SPACE_RE.sub(" ", str(value).strip())
    for fmt in _DOB_FORMATS:
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def l1_gender(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _GENDER_MAP.get(l1_text(value))


# ---------------------------------------------------------------- Level 2
def l2_name(value: Optional[str]) -> str:
    """Level 1 + controlled token canonicalisation (Mohd/Md/Mohammed -> mohammad)."""
    tokens = l1_text(value).split()
    return " ".join(config.LEVEL2_TOKEN_MAP.get(t, t) for t in tokens)


# ---------------------------------------------------------------- Level 3 helpers
def token_sort(value: str) -> str:
    """Split into words, sort alphabetically, rejoin with a single space."""
    return " ".join(sorted(value.split()))


def soundex(word: str) -> str:
    """Classic American Soundex (4 chars). Used only for blocking keys."""
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return ""
    codes = {**dict.fromkeys("bfpv", "1"), **dict.fromkeys("cgjkqsxz", "2"),
             **dict.fromkeys("dt", "3"), "l": "4", **dict.fromkeys("mn", "5"), "r": "6"}
    first = word[0].upper()
    out = []
    prev = codes.get(word[0], "")
    for ch in word[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            out.append(code)
        if ch not in "hw":
            prev = code
    return (first + "".join(out) + "000")[:4]


def phonetic_keys(name_l2: str) -> set[str]:
    """Soundex of every token of a name (order independent)."""
    return {soundex(t) for t in name_l2.split() if len(t) > 1} - {""}


def first_name(value: Optional[str]) -> str:
    """First word of the raw name, title-cased, for message templates."""
    toks = [t for t in re.split(r"\s+", str(value or "").strip()) if t]
    if not toks:
        return ""
    # skip leading honorific-like 'Kumari' when the name is reversed ('Kumari Priya')
    if len(toks) > 1 and toks[0].lower() in {"kumari", "kumar"}:
        return toks[1].strip(".").title()
    return toks[0].strip(".").title()


def valid_mobile(value) -> bool:
    s = re.sub(r"\D", "", str(value or ""))
    if len(s) == 12 and s.startswith("91"):
        s = s[2:]
    return len(s) == 10 and s[0] in "6789"
