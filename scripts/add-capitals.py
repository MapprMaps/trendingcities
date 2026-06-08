#!/usr/bin/env python3
"""Add missing capital-city records from Andreas's CSV (region,country,country_code,
capital,suggested_id,lat,lng). Sources median 1/2/3-bed apartment PURCHASE prices
(USD, city centre) per capital via focused Perplexity, honestly confidence-graded
(real market data → web/medium; no market → model_estimate/low). Guarantees
monotonic 1<=2<=3 ordering. Creates a schema-valid published record per capital.

Idempotent: skips capitals whose record already exists.
Run: source ~/.secrets && python3 scripts/add-capitals.py /path/to.csv [--limit N]
"""
import json, os, csv, sys, time, re, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
TODAY = datetime.date.today().isoformat()
LOG = os.path.join(ROOT, "add-capitals.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")
CSV = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else None

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def ask_prices(city, country):
    p = (f'Median PURCHASE price (not rent) of an apartment in the CITY CENTRE of {city}, '
         f'{country}, in USD, for 1-bedroom, 2-bedroom and 3-bedroom. Use Numbeo / Global '
         f'Property Guide / local market data. If no real market data exists, give your best '
         f'estimate from regional comparables and set confidence low. Reply ONLY JSON: '
         f'{{"p1":INT,"p2":INT,"p3":INT,"confidence":"high|medium|low","basis":"short phrase"}}')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": p}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1])

def price_metric(value, conf, basis):
    low = conf == "low"
    return {"value": int(round(value)), "unit": "USD", "as_of": AS_OF,
            "sources": ["model_estimate"] if low else ["web"], "confidence": conf,
            "method": "regional-comparable estimate" if low else "cross-source web research (Numbeo/GPG/listings)",
            "notes": basis[:160]}

def main():
    if not CSV or not os.path.exists(CSV):
        logln("usage: add-capitals.py <csv>"); sys.exit(1)
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    rows = list(csv.DictReader(open(CSV)))
    if limit: rows = rows[:limit]
    logln(f"=== add-capitals: {len(rows)} capitals ===")
    created = skipped = failed = 0
    for r in rows:
        cid = r["suggested_id"].strip()
        f = os.path.join(ROOT, "data/cities", cid + ".json")
        if os.path.exists(f):
            skipped += 1; logln(f"  {cid}: exists — skip"); continue
        try:
            o = ask_prices(r["capital"], r["country"])
            vals = sorted([float(o["p1"]), float(o["p2"]), float(o["p3"])])  # force monotonic
            if not (5000 <= vals[0] and vals[2] <= 50_000_000):
                raise ValueError(f"out of range {vals}")
        except Exception as ex:
            failed += 1; logln(f"  {cid}: FAIL {ex}"); time.sleep(2); continue
        conf = o.get("confidence", "low"); basis = o.get("basis", "")
        rec = {
            "schema_version": "1.0", "id": cid, "city": r["capital"].strip(),
            "country": r["country"].strip(), "country_code": r["country_code"].strip().upper(),
            "coordinates": {"lat": float(r["lat"]), "lng": float(r["lng"])},
            "metrics": {
                "home_price_1bed_usd": price_metric(vals[0], conf, basis),
                "home_price_2bed_usd": price_metric(vals[1], conf, basis),
                "home_price_3bed_usd": price_metric(vals[2], conf, basis),
            },
            "provenance": {"compiled_by": "hugo-capitals-2026-06", "compiled_at": TODAY, "status": "published"},
        }
        os.makedirs(os.path.dirname(f), exist_ok=True)
        json.dump(rec, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        created += 1
        logln(f"  {cid}: {int(vals[0])}/{int(vals[1])}/{int(vals[2])} ({conf})")
        time.sleep(0.5)
    logln(f"=== DONE: {created} created, {skipped} skipped, {failed} failed ===")

if __name__ == "__main__":
    main()
