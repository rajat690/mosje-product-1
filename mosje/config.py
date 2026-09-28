"""Central configuration. Values here come straight from the V3.0 spec documents.

Tune thresholds here during the build phase - the engine code reads them from this module.
"""
import os
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("MOSJE_DATA_DIR", ROOT / "data"))
OUTPUT_DIR = Path(os.environ.get("MOSJE_OUTPUT_DIR", ROOT / "output"))
# Platform copy: the scheme master ships inside the repo (data/). Override with SCHEME_MASTER_PATH.
SCHEME_MASTER_PATH = Path(os.environ.get("SCHEME_MASTER_PATH", DATA_DIR / "MoSJE_Scholarship_Master_V3.0.xlsx"))
SCHEME_MASTER_SHEET = "Fresh Scholarship Master"

RULE_VERSION = "V3.0"
LINKAGE_RULE_VERSION = "V3.0"

# Eligibility Rule V3.0, section 7.2: fixed as-of date for the whole run.
ELIGIBILITY_AS_OF_DATE = date(2026, 9, 27)
EFFECTIVE_FROM = "2026-09-27"

# Linkage Rules V3.0, section 3: weights (sum = 100)
WEIGHTS = {"dob": 30.0, "name": 25.0, "father": 20.0, "mother": 20.0, "gender": 5.0}

# Field-similarity bands used by the 56-row matrix
BAND_HIGH = 90.0      # >=90%
BAND_MID = 80.0       # 80-89.99%, below that is <80%

# Overall-score bands
OVERALL_MATCHED = 90.0
OVERALL_PROBABLE_LOW = 70.0

# Guardrail G7 - top candidate margin
G7_MIN_MARGIN = 5.0

# Level 2 controlled Indian-name normalisation (used cautiously, per spec section 2)
LEVEL2_TOKEN_MAP = {
    "mohd": "mohammad",
    "md": "mohammad",
    "mohammed": "mohammad",
    "muhammad": "mohammad",
    "mohamed": "mohammad",
    "mohamad": "mohammad",
}

# Blocking passes (spec section 4). All four spec passes include DOB.
# EXTRA_BLOCKING_PARENTS_WITHOUT_DOB is NOT in the spec; it is off by default and only
# used for the optional sensitivity run reported in the summary.
EXTRA_BLOCKING_PARENTS_WITHOUT_DOB = False

# Output limits
AUDIT_XLSX_ROW_CAP = 60000

# Synthetic data sizes
SEED = 20260927
N_FAMILIES = 5000
N_CBSE_X = 3000
N_CBSE_XII = 2000
SHARE_IN_JAN_AADHAAR = 0.85
