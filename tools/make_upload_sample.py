"""Make a small 'your own data' sample from the bundled synthetic files, WITHOUT ground truth.

Takes the first N CBSE rows and every Jan Aadhaar member of the families of their true matches (plus
some unrelated families), and changes a few values so it is not just a copy. Used by the upload tests
and for a live trial of the upload endpoints. Usage:
    python tools/make_upload_sample.py [N] [out_dir]      (defaults: 500, ./upload_sample)
"""
from __future__ import annotations

import csv
import gzip
import io
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def _read(name):
    return list(csv.DictReader(io.StringIO(gzip.decompress((DATA / name).read_bytes()).decode("utf-8"))))


def make(n: int = 500, seed: int = 7):
    rnd = random.Random(seed)
    cbse = _read("cbse_passed_2025_26.csv.gz")[:n]
    truth = {t["roll_no"]: t for t in _read("ground_truth.csv.gz")}
    ja = _read("jan_aadhaar_members.csv.gz")
    true_mids = {truth[c["roll_no"]]["true_member_id"] for c in cbse} - {""}
    fam = {m["jan_aadhaar_id"] for m in ja if m["member_id"] in true_mids}
    others = sorted({m["jan_aadhaar_id"] for m in ja} - fam)
    fam |= set(rnd.sample(others, min(len(others), n // 5)))
    ja_sub = [dict(m) for m in ja if m["jan_aadhaar_id"] in fam]
    cbse = [dict(c) for c in cbse]
    for c in cbse[::25]:                       # "modified": a few changed schools / mobiles
        c["school"] = "Uploaded Test School, " + (c["district"] or "")
        c["mobile"] = ""
    return cbse, ja_sub


def to_csv(rows) -> bytes:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "upload_sample")
    out.mkdir(parents=True, exist_ok=True)
    cbse, ja = make(n)
    (out / "my_cbse.csv").write_bytes(to_csv(cbse))
    (out / "my_jan_aadhaar.csv").write_bytes(to_csv(ja))
    print(f"wrote {len(cbse)} CBSE rows and {len(ja)} Jan Aadhaar rows to {out}/ (no ground truth)")
