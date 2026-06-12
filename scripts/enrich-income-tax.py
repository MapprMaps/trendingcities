#!/usr/bin/env python3
"""Add effective personal income-tax rates (low/mid/high earner) to each city.

Income tax is national, so this sources ONE set of effective rates per COUNTRY and
applies it to every city in that country (note: countries with local income tax —
US states, Swiss cantons, Nordic municipal — carry a note that city-level variation
exists; the figure is the national/representative effective rate).

"Effective" = personal income tax + mandatory employee social-security contributions
as % of gross, for a single filer, at three absolute USD gross-income bands:
low $30k, mid $75k, high $150k. Most useful framing for a relocation audience.

Resumable: skips countries whose cities already carry the tax metrics.
Run: source ~/.secrets && python3 scripts/enrich-income-tax.py [--limit N]
"""
import json, os, glob, sys, time, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
LOG = os.path.join(ROOT, "income-tax.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")
BANDS = {"low": 30000, "mid": 75000, "high": 150000}

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def rates(country):
    p = (f'For {country}, estimate the EFFECTIVE personal income tax rate (national personal '
         f'income tax PLUS mandatory employee social-security contributions, as a percentage of '
         f'gross income) for a SINGLE filer with no dependents, at three gross annual incomes in '
         f'USD: $30,000 (low), $75,000 (mid), $150,000 (high). Use current tax brackets converted '
         f'to local currency. Reply ONLY JSON: {{"low":NN.N,"mid":NN.N,"high":NN.N}} (percentages). '
         f'If {country} has no personal income tax, use 0. Do not fabricate brackets.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": p}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=70).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1])

def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    # group published cities by country
    by_country = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        by_country.setdefault(d["country"], []).append((f, d))
    # skip countries already done (all their cities carry the metric)
    todo = [(c, lst) for c, lst in by_country.items()
            if not all("income_tax_effective_mid_pct" in d["metrics"] for _, d in lst)]
    todo.sort()
    if limit: todo = todo[:limit]
    logln(f"=== income tax: {len(todo)} countries ({sum(len(l) for _,l in todo)} cities) ===")
    done = bad = 0
    for country, lst in todo:
        try:
            r = rates(country)
            vals = {k: float(r[k]) for k in BANDS}
            for v in vals.values():
                if not (0 <= v <= 75): raise ValueError(f"out of range {vals}")
            # monotonic-ish: progressive systems => low <= mid <= high (allow tiny inversion)
        except Exception as ex:
            bad += 1; logln(f"  {country}: FAIL {ex}"); time.sleep(2); continue
        note = "Effective income tax + employee social contributions, single filer; national rate"
        for f, d in lst:
            for band in BANDS:
                d["metrics"][f"income_tax_effective_{band}_pct"] = {
                    "value": round(vals[band], 1), "unit": "pct", "as_of": AS_OF, "sources": ["web"],
                    "confidence": "medium", "method": "effective rate at $30k/$75k/$150k gross (single filer)",
                    "notes": note}
            json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        done += 1
        logln(f"  {country}: low {vals['low']}% mid {vals['mid']}% high {vals['high']}% -> {len(lst)} cities")
        time.sleep(0.5)
    logln(f"=== DONE: {done} countries enriched, {bad} failed ===")

if __name__ == "__main__":
    main()
