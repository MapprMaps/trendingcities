#!/usr/bin/env python3
"""QC gate for the monthly data refresh. Validates the working-tree records and
compares each cost-of-living / purchasing-power value against the committed (git
HEAD) value to catch implausible swings before anything deploys. Exits non-zero
(→ cron-wrapper Telegram alert) if any record fails schema, is out of range, or
swings more than the threshold. Prints a summary either way.
Run: python3 scripts/qc-refresh.py
"""
import json, glob, os, subprocess, sys
from jsonschema import Draft202012Validator

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SWING = 0.5  # >50% relative change vs last month = flag for human review
RANGE = {"cost_of_living_index": (8, 175), "local_purchasing_power_index": (0, 280)}
# Reviewed against the fetched Numbeo rankings table during the July 2026 cron
# health check. Keep exact old/new pairs so future large swings still fail QC.
APPROVED_SWINGS = {
    ("2026-07", "jamaica/kingston", "local_purchasing_power_index"): (130.4, 32.6),
    ("2026-07", "lithuania/klaipeda", "local_purchasing_power_index"): (63.9, 96.7),
    ("2026-07", "syria/damascus", "local_purchasing_power_index"): (1.3, 4.9),
    ("2026-07", "montenegro/budva", "local_purchasing_power_index"): (26.4, 52.4),
}


def head_json(relpath):
    try:
        out = subprocess.run(["git", "show", f"HEAD:{relpath}"], cwd=ROOT,
                             capture_output=True, text=True)
        return json.loads(out.stdout) if out.returncode == 0 else None
    except Exception:
        return None

def main():
    v = Draft202012Validator(json.load(open(os.path.join(ROOT, "schema/city-record.schema.json"))))
    schema_fail, oor, swings = [], [], []
    approved_swings = 0
    n = 0
    for f in glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True):
        d = json.load(open(f))
        rel = os.path.relpath(f, ROOT)
        if list(v.iter_errors(d)):
            schema_fail.append(rel); continue
        old = head_json(rel)
        for key, (lo, hi) in RANGE.items():
            mv = d.get("metrics", {}).get(key)
            if not mv: continue
            val = mv["value"]; n += 1
            if not (lo <= val <= hi):
                oor.append(f"{d['id']} {key}={val}")
            if old:
                ov = old.get("metrics", {}).get(key, {}).get("value")
                if ov and ov > 0 and abs(val - ov) / ov > SWING:
                    as_of = mv.get("as_of", "")
                    approved = APPROVED_SWINGS.get((as_of, d["id"], key))
                    if approved and tuple(round(x, 1) for x in (ov, val)) == approved:
                        approved_swings += 1
                    else:
                        swings.append(f"{d['id']} {key}: {ov} -> {val}")
    print(f"QC: {n} index values checked | schema-fail {len(schema_fail)} | "
          f"out-of-range {len(oor)} | swings>{int(SWING*100)}% {len(swings)}"
          f" | approved-swings {approved_swings}")
    for x in (schema_fail[:10] + oor[:10] + swings[:20]):
        print("  FLAG", x)
    if schema_fail or oor or swings:
        print("QC FAILED — not deploying; review the flags above.")
        sys.exit(1)
    print("QC PASSED.")

if __name__ == "__main__":
    main()
