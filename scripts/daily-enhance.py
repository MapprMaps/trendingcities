#!/usr/bin/env python3
"""Daily incremental enhancement engine for TrendingCities.

Each run deepens REAL data on a small batch of cities, prioritising the pages
that are actually getting traffic (Plausible). Current task = fill rents (1 & 3
-bed city-centre USD) for cities that have a cost-of-living index but no rents,
and derive price_to_rent_ratio. Resumable + analytics-weighted + QC-gated.

Over ~17 days this fills rents for all ~250 remaining cities; when the rents
backlog is empty it exits cleanly (next task gets added then). Rents sourced via
focused per-city Numbeo lookups (Perplexity sonar-pro, one city/call = reliable);
null fields are skipped, never fabricated.

Run: source ~/.secrets && python3 scripts/daily-enhance.py [--batch 15]
Writes a one-line Telegram summary to Andreas on success.
"""
import json, os, glob, sys, time, re, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
import datetime
AS_OF = os.environ.get("TC_AS_OF") or datetime.date.today().strftime("%Y-%m")
LOG = os.path.join(ROOT, "daily-enhance.log")
PPLX = os.environ.get("PERPLEXITY_API_KEY", "")
PLAUS = os.environ.get("PLAUSIBLE_API_KEY", "")
CHAT_ID = "6878096625"

def logln(m):
    stamp = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    line = f"{stamp} {m}"
    print(line, flush=True)
    with open(LOG, "a") as fh: fh.write(line + "\n")

def gsc_opportunity_slugs():
    """City slugs with Google Search Console impressions but weak position — real
    'we could rank for this' opportunity. Activates automatically once the service
    account (gemini-burn-bot@sitemetrics-458214) is added to the GSC property.
    Falls back to empty (→ Plausible) on any error or until access/data exist."""
    prop = os.environ.get("TC_GSC_PROPERTY", "sc-domain:trendingcities.com")
    try:
        import subprocess as sp
        tok = sp.run(["gcloud", "auth", "print-access-token",
                      "--scopes=https://www.googleapis.com/auth/webmasters.readonly"],
                     capture_output=True, text=True).stdout.strip()
        if not tok: return set()
        end = datetime.date.today(); start = end - datetime.timedelta(days=28)
        body = json.dumps({"startDate": start.isoformat(), "endDate": end.isoformat(),
            "dimensions": ["page"], "rowLimit": 500}).encode()
        url = f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(prop, safe='')}/searchAnalytics/query"
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as ex:
        logln(f"GSC unavailable ({ex}) — using Plausible only"); return set()
    slugs = set()
    for row in r.get("rows", []):
        # opportunity = has impressions but ranking past page 1 (position > 8)
        if row.get("impressions", 0) >= 3 and row.get("position", 99) > 8:
            m = re.search(r'/city/([a-z0-9-]+/[a-z0-9-]+)/?$', row["keys"][0])
            if m: slugs.add(m.group(1))
    if slugs: logln(f"GSC: {len(slugs)} city pages with ranking opportunity")
    return slugs

def plausible_traffic_slugs():
    """City slugs (country/city) with traffic in the last 14 days, for prioritising."""
    if not PLAUS: return set()
    body = json.dumps({"site_id": "trendingcities.com", "metrics": ["pageviews"],
        "date_range": "14d", "dimensions": ["event:page"], "pagination": {"limit": 200}}).encode()
    req = urllib.request.Request("https://my.sitemetrics.app/api/v2/query", data=body,
        headers={"Authorization": "Bearer " + PLAUS, "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read())
    except Exception as ex:
        logln(f"plausible fetch failed ({ex}) — proceeding without traffic priority"); return set()
    slugs = set()
    for row in r.get("results", []):
        m = re.match(r'^/city/([a-z0-9-]+/[a-z0-9-]+)/?$', row["dimensions"][0])
        if m: slugs.add(m.group(1))
    return slugs

def rents(city, country):
    prompt = (f'Numbeo publishes current rent data for {city}, {country}. Give its average '
              f'monthly rent in the CITY CENTRE for a 1-bedroom apartment and a 3-bedroom '
              f'apartment, converted to USD. Reply ONLY as JSON: '
              f'{{"rent_1bed_usd":NNNN or null,"rent_3bed_usd":NNNN or null}}. Provide the actual '
              f'Numbeo figures; use null for a field ONLY if {city} genuinely has no Numbeo rent '
              f'page (rare). Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + PPLX, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1])

def metric(value, unit, sources, conf, method=None, notes=None):
    mv = {"value": value, "unit": unit, "as_of": AS_OF, "sources": sources, "confidence": conf}
    if method: mv["method"] = method
    if notes: mv["notes"] = notes
    return mv

def notify(text):
    try:
        env = {}
        with open("/home/claude-svc/.config/claude-bots/trendingcities.env") as fh:
            for ln in fh:
                if "=" in ln and not ln.strip().startswith("#"):
                    k, v = ln.strip().split("=", 1); env[k] = v
        tok = env.get("TELEGRAM_BOT_TOKEN", "")
        if not tok: return
        data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.telegram.org/bot{tok}/sendMessage", data=data), timeout=20).read()
    except Exception as ex:
        logln(f"telegram notify failed: {ex}")

import urllib.parse

def main():
    batch = int(sys.argv[sys.argv.index("--batch")+1]) if "--batch" in sys.argv else 15
    # backlog: published top-level cities with COL but no rents
    backlog = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        m = d.get("metrics", {})
        if "cost_of_living_index" in m and "rent_3bed_usd_month" not in m:
            backlog.append((f, d))
    if not backlog:
        logln("rents backlog empty — nothing to do this cycle"); return
    # prioritise: GSC ranking-opportunity pages → Plausible-traffic pages → rest
    gsc = gsc_opportunity_slugs()
    traffic = plausible_traffic_slugs()
    backlog.sort(key=lambda fd: (fd[1]["id"] not in gsc, fd[1]["id"] not in traffic, fd[1]["id"]))
    todo = backlog[:batch]
    logln(f"=== daily-enhance: {len(backlog)} cities need rents; doing {len(todo)} "
          f"({sum(1 for _,d in todo if d['id'] in gsc)} GSC-opportunity, "
          f"{sum(1 for _,d in todo if d['id'] in traffic)} with traffic) ===")
    placed = 0; examples = []
    for f, d in todo:
        try:
            o = rents(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: ERROR {ex}"); time.sleep(2); continue
        m = d["metrics"]; n = 0
        r1, r3 = o.get("rent_1bed_usd"), o.get("rent_3bed_usd")
        if r1 and 50 < float(r1) < 30000:
            m["rent_1bed_usd_month"] = metric(int(round(float(r1))), "USD_per_month", ["numbeo"], "medium",
                notes="Avg monthly rent, 1-bed city centre"); n += 1
        if r3 and 50 < float(r3) < 60000:
            m["rent_3bed_usd_month"] = metric(int(round(float(r3))), "USD_per_month", ["numbeo"], "medium",
                notes="Avg monthly rent, 3-bed city centre"); n += 1
            p3 = m.get("home_price_3bed_usd", {}).get("value")
            if p3:
                m["price_to_rent_ratio"] = metric(round(p3/(float(r3)*12), 1), "ratio", ["model_estimate"],
                    "medium", method="home_price_3bed_usd / (12 * rent_3bed_usd_month)",
                    notes="Years of 3-bed rent to equal the 3-bed purchase price")
        if n:
            json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
            placed += 1
            if len(examples) < 4: examples.append(d["city"])
            logln(f"  {d['id']}: rent1 {r1} rent3 {r3}")
        else:
            logln(f"  {d['id']}: no rent data — skipped")
        time.sleep(0.6)
    remaining = len(backlog) - placed
    logln(f"=== DONE: rents added to {placed} cities, {remaining} still need rents ===")
    if placed:
        notify(f"🏙️ TrendingCities daily: added rents to {placed} cities "
               f"({', '.join(examples)}{'…' if placed>len(examples) else ''}). {remaining} cities left to enrich.")

if __name__ == "__main__":
    main()
