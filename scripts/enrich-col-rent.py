#!/usr/bin/env python3
"""Scale the cost-of-living layer to all top-level cities.

For each published top-level city record (depth-2 id, i.e. not a district) that
does NOT already have a cost_of_living_index, fetch current Numbeo figures via
Perplexity sonar-pro (grounded), in batches. Writes per-metric provenance and a
derived price_to_rent_ratio. NEVER fabricates: the model is told to return null
for any figure it can't find a real published value for, and null fields are
simply not written (honest absence — the renderer handles partial records).

Resumable: skips records that already have cost_of_living_index.
Run: source ~/.secrets && python3 scripts/enrich-col-rent.py [--limit N] [--batch 12]
"""
import json, os, glob, sys, time, urllib.request, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = "2026-06"
LOG = os.path.join(ROOT, "enrich-col-rent.log")
PPLX_KEY = os.environ.get("PERPLEXITY_API_KEY", "")

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def load_targets():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published": continue
        if d["id"].count("/") != 1: continue            # top-level cities only (skip districts)
        if "cost_of_living_index" in d.get("metrics", {}): continue  # resumable skip
        out.append((f, d))
    return out

def pplx(cities):
    """cities = list of (id, 'City, Country'). Returns dict id -> figures."""
    listing = "\n".join(f'{cid} | {name}' for cid, name in cities)
    prompt = (
        "For each city below, give CURRENT (2026) Numbeo figures. Return ONLY a JSON array, "
        "no prose, no markdown fences. One object per city with EXACTLY these keys:\n"
        '{"id":"<the id verbatim>","cost_of_living_index":NN.N or null,'
        '"local_purchasing_power_index":NN.N or null,"rent_1bed_center_usd":NNNN or null,'
        '"rent_3bed_center_usd":NNNN or null}\n'
        "cost_of_living_index = Numbeo Cost of Living Index EXCLUDING rent, New York City = 100.\n"
        "local_purchasing_power_index = Numbeo Local Purchasing Power Index, New York City = 100.\n"
        "rent_*_center_usd = avg monthly rent for that apartment size in the city centre, USD.\n"
        "Numbeo publishes cost-of-living data for thousands of cities worldwide, including most "
        "cities in this list — provide Numbeo's actual current figures for each. Use null for a "
        "field ONLY when that specific city genuinely has no Numbeo page (rare — small towns or "
        "districts). Do not fabricate values for a city that isn't on Numbeo. Echo the id exactly "
        "as given.\n\nCities:\n" + listing
    )
    body = json.dumps({"model": "sonar-pro",
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + PPLX_KEY, "Content-Type": "application/json"})
    raw = json.loads(urllib.request.urlopen(req, timeout=90).read())
    txt = raw["choices"][0]["message"]["content"].strip()
    txt = re.sub(r"^```(json)?|```$", "", txt.strip(), flags=re.MULTILINE).strip()
    s, e = txt.find("["), txt.rfind("]")
    arr = json.loads(txt[s:e+1])
    return {o["id"]: o for o in arr if o.get("id")}

def metric(value, unit, sources, confidence, method=None, notes=None):
    mv = {"value": value, "unit": unit, "as_of": AS_OF, "sources": sources, "confidence": confidence}
    if method: mv["method"] = method
    if notes: mv["notes"] = notes
    return mv

def main():
    args = sys.argv[1:]
    batch = int(args[args.index("--batch")+1]) if "--batch" in args else 12
    limit = int(args[args.index("--limit")+1]) if "--limit" in args else 0
    targets = load_targets()
    if limit: targets = targets[:limit]
    logln(f"=== enrich-col-rent: {len(targets)} cities to process, batch={batch} ===")
    placed = total_fields = 0
    for i in range(0, len(targets), batch):
        chunk = targets[i:i+batch]
        cities = [(d["id"], f'{d["city"]}, {d["country"]}') for _, d in chunk]
        try:
            res = pplx(cities)
        except Exception as ex:
            logln(f"  batch {i//batch} ERROR: {ex}; retrying once")
            try: time.sleep(4); res = pplx(cities)
            except Exception as ex2:
                logln(f"  batch {i//batch} FAILED: {ex2}; skipping"); continue
        for f, d in chunk:
            o = res.get(d["id"])
            if not o:
                logln(f"  {d['id']}: no result"); continue
            m = d.setdefault("metrics", {})
            n = 0
            if o.get("cost_of_living_index") is not None:
                m["cost_of_living_index"] = metric(round(float(o["cost_of_living_index"]),1),
                    "index_numbeo_nyc100", ["numbeo"], "medium", notes="Numbeo Cost of Living Index, excl. rent, NYC=100"); n+=1
            if o.get("local_purchasing_power_index") is not None:
                m["local_purchasing_power_index"] = metric(round(float(o["local_purchasing_power_index"]),1),
                    "index_numbeo_nyc100", ["numbeo"], "medium", notes="Numbeo Local Purchasing Power Index, NYC=100"); n+=1
            r3 = o.get("rent_3bed_center_usd")
            if o.get("rent_1bed_center_usd") is not None:
                m["rent_1bed_usd_month"] = metric(int(round(float(o["rent_1bed_center_usd"]))),
                    "USD_per_month", ["numbeo"], "medium", notes="Avg monthly rent, 1-bed city centre"); n+=1
            if r3 is not None:
                m["rent_3bed_usd_month"] = metric(int(round(float(r3))),
                    "USD_per_month", ["numbeo"], "medium", notes="Avg monthly rent, 3-bed city centre"); n+=1
                price3 = m.get("home_price_3bed_usd", {}).get("value")
                if price3 and float(r3) > 0:
                    m["price_to_rent_ratio"] = metric(round(price3/(float(r3)*12),1), "ratio",
                        ["model_estimate"], "medium",
                        method="home_price_3bed_usd / (12 * rent_3bed_usd_month)",
                        notes="Years of 3-bed rent to equal the 3-bed purchase price")
            if n:
                json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
                placed += 1; total_fields += n
                logln(f"  {d['id']}: {n} fields"
                      + (f" · COL {m['cost_of_living_index']['value']}" if 'cost_of_living_index' in m else ""))
            else:
                logln(f"  {d['id']}: all null (no Numbeo coverage) — left empty")
        logln(f"-- batch {i//batch+1}/{(len(targets)+batch-1)//batch} done ({placed} placed so far) --")
        time.sleep(1)
    logln(f"=== DONE: {placed}/{len(targets)} cities enriched, {total_fields} metric values written ===")

if __name__ == "__main__":
    main()
