#!/usr/bin/env python3
"""Multi-source CONSENSUS price research for the still-low-confidence cities.

For each low-confidence price city, ask for the price/m² (buy, city centre, USD) as
reported SEPARATELY by each source, then accept a value ONLY when >=2 genuinely
INDEPENDENT source families agree (within ~1.6x spread). This is the fix for the
cities the single-source cross-check couldn't resolve: one number can be a luxury-
skew/hallucination, but independent sources agreeing is real signal.

Key guard: Livingcost.org mirrors Numbeo, so they're ONE family — counting them as
two would be false consensus (this is exactly what made Luanda look corroborated).
Families: numbeo(+livingcost), globalpropertyguide, expatistan, listings(properstar/
wise/realtor/local), numbeo-independent others. No consensus -> keep estimate.

Run: source ~/.secrets && python3 scripts/research-prices-consensus.py [--limit N]
"""
import json, os, glob, sys, time, urllib.request, datetime, statistics

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
LOG = os.path.join(ROOT, "research-prices.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")
SQM = {"1": 50, "2": 78, "3": 105}

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def family(name):
    n = name.lower()
    if "numbeo" in n or "livingcost" in n or "living cost" in n: return "numbeo"
    if "global property" in n or "globalproperty" in n or "gpg" in n: return "gpg"
    if "expatistan" in n: return "expatistan"
    if any(k in n for k in ("properstar", "wise", "realtor", "listing", "local", "lamudi", "encuentra24", "idealista")): return "listings"
    return n.strip()[:12] or "other"

def ask_sources(city, country):
    p = (f'For {city}, {country}, report the CURRENT price per square meter in USD to BUY an '
         f'apartment in the CITY CENTRE, as reported SEPARATELY by each of these sources where it '
         f'genuinely has data: Numbeo, Global Property Guide, Expatistan, Properstar, local '
         f'real-estate listing portals. Return ONLY JSON: {{"sources":[{{"name":"...","ppsqm":INT}}]}}. '
         f'Include a source ONLY if it actually has a value; never invent. Omit sources without data.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": p}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=70).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1]).get("sources", [])

def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    targets = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        if d.get("metrics", {}).get("home_price_3bed_usd", {}).get("confidence") == "low":
            targets.append((f, d))
    if limit: targets = targets[:limit]
    logln(f"=== consensus research: {len(targets)} low-confidence cities ===")
    consensus = single = none = 0
    for f, d in targets:
        try:
            srcs = ask_sources(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: ERROR {ex}"); time.sleep(2); continue
        # collapse to one value per independent family (average within a family)
        fam = {}
        for s in srcs:
            try: v = float(s.get("ppsqm"))
            except (TypeError, ValueError): continue
            if 150 <= v <= 35000: fam.setdefault(family(s.get("name", "")), []).append(v)
        famvals = {k: statistics.mean(v) for k, v in fam.items()}
        names = ",".join(sorted(famvals))
        if len(famvals) < 2:
            (single if famvals else none).__class__  # no-op for clarity
            if famvals: single += 1; logln(f"  {d['id']}: only 1 family ({names}) — no consensus, kept estimate")
            else: none += 1; logln(f"  {d['id']}: no source data — kept estimate")
            time.sleep(0.5); continue
        vals = sorted(famvals.values())
        spread = vals[-1] / vals[0]
        if spread > 1.6:
            logln(f"  {d['id']}: {len(famvals)} families disagree (spread {spread:.1f}x: {names}) — kept estimate")
            none += 1; time.sleep(0.5); continue
        ps = statistics.median(vals)
        old3 = d["metrics"]["home_price_3bed_usd"]["value"]
        note = f"Cross-source consensus of {len(famvals)} independent sources ({names}): ${int(ps)}/m² × typical size"
        for bed, sqm in SQM.items():
            d["metrics"][f"home_price_{bed}bed_usd"] = {
                "value": int(round(ps * sqm / 1000) * 1000), "unit": "USD", "as_of": AS_OF,
                "sources": ["web"], "confidence": "medium",
                "method": f"consensus price/m² ({len(famvals)} sources) × typical apartment size", "notes": note}
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        consensus += 1
        new3 = d["metrics"]["home_price_3bed_usd"]["value"]
        logln(f"  {d['id']}: CONSENSUS {len(famvals)} src ({names}) ${int(ps)}/m² -> 3bed {old3}->{new3} [medium]")
        time.sleep(0.5)
    logln(f"=== DONE: {consensus} consensus-upgraded, {single} single-source (kept), {none} no-data/disagree (kept) ===")

if __name__ == "__main__":
    main()
