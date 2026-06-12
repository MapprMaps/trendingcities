#!/usr/bin/env python3
"""Add annual-mean PM2.5 air quality (µg/m³) to each city via focused per-city
research (WHO / IQAir / national monitoring). Per-city because air quality varies
a lot within a country. Range-guarded, null-safe (never fabricates), resumable.
Run: source ~/.secrets && python3 scripts/enrich-air-quality.py [--limit N] [--batch N]
"""
import json, os, glob, sys, time, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
LOG = os.path.join(ROOT, "air-quality.log")
KEY = os.environ.get("PERPLEXITY_API_KEY", "")

def logln(m):
    print(m, flush=True)
    with open(LOG, "a") as fh: fh.write(m + "\n")

def pm25(city, country):
    p = (f'What is the recent ANNUAL MEAN PM2.5 air pollution level (µg/m³) for {city}, {country}? '
         f'Use WHO / IQAir World Air Quality Report / national monitoring data. Reply ONLY JSON: '
         f'{{"pm25":NN.N or null}}. Use null only if {city} genuinely has no measured data. Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": p}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1]).get("pm25")

def main():
    limit = int(sys.argv[sys.argv.index("--limit")+1]) if "--limit" in sys.argv else 0
    targets = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        if "air_quality_pm25_ugm3" in d.get("metrics", {}): continue
        targets.append((f, d))
    if limit: targets = targets[:limit]
    logln(f"=== air quality: {len(targets)} cities ===")
    placed = no_data = 0
    for f, d in targets:
        try:
            v = pm25(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: ERROR {ex}"); time.sleep(2); continue
        if v is None or not (1 <= float(v) <= 300):
            no_data += 1; logln(f"  {d['id']}: no PM2.5 data — skipped"); time.sleep(0.4); continue
        d["metrics"]["air_quality_pm25_ugm3"] = {
            "value": round(float(v), 1), "unit": "ugm3", "as_of": AS_OF, "sources": ["web"],
            "confidence": "medium", "method": "annual mean PM2.5 (WHO/IQAir/national monitoring)",
            "notes": "Annual mean PM2.5; WHO guideline is 5 µg/m³"}
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        placed += 1; logln(f"  {d['id']}: PM2.5 {v}")
        time.sleep(0.4)
    logln(f"=== DONE: {placed} cities got PM2.5, {no_data} no data ===")

if __name__ == "__main__":
    main()
