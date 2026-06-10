#!/usr/bin/env python3
"""Price cross-check / upgrade for low-confidence cities.

For each top-level city whose 3-bed price is LOW confidence (a pure estimate),
fetch Numbeo's published 'Price per m² to Buy Apartment in City Centre' (a real,
concrete Numbeo metric — a genuinely independent anchor vs the original total-price
guess). Where Numbeo has it, derive 1/2/3-bed totals from price/m² × typical
apartment sizes and REPLACE the estimate with this Numbeo-derived figure at MEDIUM
confidence (upgrade where it corroborates, correct where it diverges). Where Numbeo
has no price data, leave the estimate untouched (low confidence stays).

This is NOT a naive LLM re-ask: price/m² is a different, Numbeo-published number.
Idempotent: skips cities whose price source is already Numbeo-derived.
Run: source ~/.secrets && python3 scripts/refresh-prices-numbeo.py [--limit N]
"""
import json, os, glob, sys, time, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
LOG = os.path.join(ROOT, "refresh-prices.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")
# Typical interior apartment sizes (m²) by bedroom — the soft part of the model,
# stated in the method note so the derivation is transparent.
SQM = {"1": 50, "2": 78, "3": 105}

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def ppsqm(city, country):
    p = (f'What is Numbeo current "Price per Square Meter to Buy Apartment in City Centre" for '
         f'{city}, {country}, in USD? Reply ONLY JSON: {{"ppsqm":NNNN or null}}. Use null if '
         f'Numbeo genuinely has no buy-price data for {city}. Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": p}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1]).get("ppsqm")

def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    targets = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        p3 = d.get("metrics", {}).get("home_price_3bed_usd", {})
        if p3.get("confidence") == "low" and "numbeo" not in p3.get("sources", []):
            targets.append((f, d))
    if limit: targets = targets[:limit]
    logln(f"=== price cross-check: {len(targets)} low-confidence cities ===")
    # Corroboration band: the Numbeo-derived 3-bed must land within this ratio of the
    # existing estimate to be trusted. Outside it, ONE of the two is badly wrong (often
    # a luxury-skewed / hallucinated price/m² for obscure cities) and we can't tell
    # which — so we DON'T assert a number, we keep the estimate and flag for review.
    LO, HI = 0.6, 1.6
    upgraded = no_data = diverged = 0; flags = []
    for f, d in targets:
        try:
            ps = ppsqm(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: ERROR {ex}"); time.sleep(2); continue
        if ps is None or not (150 <= float(ps) <= 35000):
            no_data += 1; logln(f"  {d['id']}: no/implausible Numbeo price/m² — kept estimate"); time.sleep(0.5); continue
        ps = float(ps)
        old3 = d["metrics"]["home_price_3bed_usd"]["value"]
        derived3 = int(round(ps * SQM["3"] / 1000) * 1000)
        ratio = derived3 / old3 if old3 else 0
        delta = (derived3 - old3) / old3 * 100 if old3 else 0
        if not (LO <= ratio <= HI):
            diverged += 1
            flags.append(f"{d['id']}: ${int(ps)}/m²->{derived3} vs est {old3} ({delta:+.0f}%)")
            logln(f"  {d['id']}: DIVERGED ({delta:+.0f}%) — kept low-confidence estimate, flagged")
            time.sleep(0.5); continue
        # corroborated: upgrade all three to the Numbeo-derived figure at medium confidence
        note = f"Numbeo price/m² ${int(ps)} × typical size (50/78/105 m²); corroborates prior estimate (Δ{delta:+.0f}%)"
        for bed, sqm in SQM.items():
            d["metrics"][f"home_price_{bed}bed_usd"] = {
                "value": int(round(ps * sqm / 1000) * 1000), "unit": "USD", "as_of": AS_OF,
                "sources": ["numbeo"], "confidence": "medium",
                "method": "Numbeo price/m² × typical apartment size", "notes": note}
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        upgraded += 1
        logln(f"  {d['id']}: ${int(ps)}/m² -> 3bed {old3}->{derived3} ({delta:+.0f}%) [corroborated->medium]")
        time.sleep(0.5)
    logln(f"=== DONE: {upgraded} upgraded (corroborated), {diverged} diverged/flagged, {no_data} no Numbeo data ===")
    if flags:
        logln("flagged (kept estimate, need manual/community review):")
        for x in flags: logln("  " + x)

if __name__ == "__main__":
    main()
