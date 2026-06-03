#!/usr/bin/env python3
"""Proof batch: merge cost-of-living + purchasing-power + rent metrics into 12
flagship city records, and derive price_to_rent_ratio. Real figures sourced from
Numbeo (current, 2026) via grounded research. Each metric carries its own
provenance (source + as_of + confidence). Idempotent: re-running overwrites the
same keys, leaves all other metrics/fields untouched.
Run: python3 scripts/merge-col-rent-proof.py
"""
import json, os, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = "2026-06"

# slug -> (cost_of_living_index, local_purchasing_power_index, rent_1bed_usd, rent_3bed_usd)
DATA = {
    "united-states/new-york":        (100.0, 100.0, 4368, 9454),
    "united-kingdom/london":         (90.2,  88.5,  2790, 5220),
    "france/paris":                  (84.3,  73.4,  1610, 3200),
    "germany/berlin":                (73.1,  91.2,  1380, 2420),
    "spain/barcelona":               (62.0,  62.5,  1270, 2200),
    "spain/madrid":                  (61.4,  70.3,  1210, 2100),
    "netherlands/amsterdam":         (84.7,  88.0,  2200, 3900),
    "portugal/lisbon":               (58.9,  49.8,  1350, 2350),
    "japan/tokyo":                   (71.2,  81.0,  1160, 2600),
    "thailand/bangkok":              (44.3,  32.1,  680,  1360),
    "united-arab-emirates/dubai":    (62.1,  104.3, 1950, 3560),
    "mexico/mexico-city":            (38.9,  36.7,  860,  1680),
}

def metric(value, unit, sources, confidence, method=None, notes=None):
    mv = {"value": value, "unit": unit, "as_of": AS_OF,
          "sources": sources, "confidence": confidence}
    if method: mv["method"] = method
    if notes: mv["notes"] = notes
    return mv

def main():
    done = 0
    for slug, (col, lpp, rent1, rent3) in DATA.items():
        f = os.path.join(ROOT, "data/cities", slug + ".json")
        if not os.path.exists(f):
            print(f"  MISSING {slug}"); continue
        d = json.load(open(f))
        m = d.setdefault("metrics", {})
        m["cost_of_living_index"] = metric(col, "index_numbeo_nyc100", ["numbeo"], "medium",
                                            notes="Numbeo Cost of Living Index, excl. rent, NYC=100")
        m["local_purchasing_power_index"] = metric(lpp, "index_numbeo_nyc100", ["numbeo"], "medium",
                                            notes="Numbeo Local Purchasing Power Index, NYC=100")
        m["rent_1bed_usd_month"] = metric(rent1, "USD_per_month", ["numbeo"], "medium",
                                            notes="Avg monthly rent, 1-bed city centre")
        m["rent_3bed_usd_month"] = metric(rent3, "USD_per_month", ["numbeo"], "medium",
                                            notes="Avg monthly rent, 3-bed city centre")
        # Derived: years of rent to equal the 3-bed purchase price.
        price3 = m.get("home_price_3bed_usd", {}).get("value")
        if price3 and rent3:
            ratio = round(price3 / (rent3 * 12), 1)
            m["price_to_rent_ratio"] = metric(ratio, "ratio", ["model_estimate"], "medium",
                method="home_price_3bed_usd / (12 * rent_3bed_usd_month)",
                notes="Years of 3-bed rent to equal the 3-bed purchase price")
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False)
        open(f, "a").write("\n")
        done += 1
        print(f"  {slug}: COL {col} · LPP {lpp} · rent1 ${rent1} · rent3 ${rent3}"
              + (f" · P/R {m['price_to_rent_ratio']['value']}×" if 'price_to_rent_ratio' in m else ""))
    print(f"DONE: {done} records enriched with cost-of-living/rent/purchasing-power")

if __name__ == "__main__":
    main()
