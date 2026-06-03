#!/usr/bin/env python3
"""Long-tail cost-of-living fill: for top-level cities NOT in Numbeo's ranked
table (no cost_of_living_index yet), fetch COL + LPP via focused per-city
Perplexity calls (one city at a time = far more reliable than batch). Marked
confidence 'low' to honestly distinguish from the canonical-table data, and the
model is told to return null (→ skipped) for places with no real Numbeo page —
so regions/aggregates mis-listed as cities (Swiss cantons, 'Cambodia combined')
are left empty rather than fabricated.

Resumable: skips records that already have cost_of_living_index.
Run: source ~/.secrets && python3 scripts/enrich-col-longtail.py [--limit N]
"""
import json, os, glob, sys, time, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = "2026-06"
LOG = os.path.join(ROOT, "enrich-col-longtail.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def ask(city, country):
    prompt = (f'What is the current Numbeo Cost of Living Index (NYC=100, excluding rent) and '
              f'Local Purchasing Power Index (NYC=100) for {city}, {country}? Reply ONLY as JSON: '
              f'{{"col":NN.N or null,"lpp":NN.N or null}}. Use null for a field only if {city} '
              f'genuinely has no Numbeo page or that index is unavailable. Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1])

def metric(value, notes):
    return {"value": round(float(value), 1), "unit": "index_numbeo_nyc100", "as_of": AS_OF,
            "sources": ["numbeo"], "confidence": "low",
            "method": "perplexity-grounded (not in Numbeo ranked table)", "notes": notes}

def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    targets = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published": continue
        if d["id"].count("/") != 1: continue
        if "cost_of_living_index" in d.get("metrics", {}): continue
        targets.append((f, d))
    if limit: targets = targets[:limit]
    logln(f"=== long-tail: {len(targets)} cities ===")
    placed = nulls = 0
    for f, d in targets:
        try:
            o = ask(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: ERROR {ex}"); time.sleep(2); continue
        m = d.setdefault("metrics", {}); n = 0
        if o.get("col") is not None:
            m["cost_of_living_index"] = metric(o["col"], "Numbeo Cost of Living Index, excl. rent, NYC=100"); n += 1
        if o.get("lpp") is not None:
            m["local_purchasing_power_index"] = metric(o["lpp"], "Numbeo Local Purchasing Power Index, NYC=100"); n += 1
        if n:
            json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
            placed += 1; logln(f"  {d['id']}: COL {o.get('col')} LPP {o.get('lpp')}")
        else:
            nulls += 1; logln(f"  {d['id']}: null (not on Numbeo / aggregate) — left empty")
        time.sleep(0.6)
    logln(f"=== DONE: {placed} filled, {nulls} left empty ===")

if __name__ == "__main__":
    main()
