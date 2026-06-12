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

def col_lpp(city, country):
    prompt = (f'Numbeo publishes cost-of-living data for {city}, {country}. Give its current '
              f'Cost of Living Index (NYC=100, excluding rent) and Local Purchasing Power Index '
              f'(NYC=100). Reply ONLY as JSON: {{"col":NN.N or null,"lpp":NN.N or null}}. Provide '
              f'the actual Numbeo figures; use null only if {city} genuinely has no Numbeo page. '
              f'Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + PPLX, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1])

def air_pm25(city, country):
    prompt = (f'Recent ANNUAL MEAN PM2.5 air pollution (µg/m³) for {city}, {country} per WHO/IQAir/'
              f'national monitoring. Reply ONLY JSON: {{"pm25":NN.N or null}}. Null only if no '
              f'measured data exists. Do not fabricate.')
    body = json.dumps({"model": "sonar-pro", "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.perplexity.ai/chat/completions", data=body,
        headers={"Authorization": "Bearer " + PPLX, "Content-Type": "application/json"})
    txt = json.loads(urllib.request.urlopen(req, timeout=60).read())["choices"][0]["message"]["content"]
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e+1]).get("pm25")

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

def load_published_cities():
    out = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published" or d["id"].count("/") != 1: continue
        out.append((f, d))
    return out

def prioritise(backlog, gsc, traffic):
    backlog.sort(key=lambda fd: (fd[1]["id"] not in gsc, fd[1]["id"] not in traffic, fd[1]["id"]))
    return backlog

def fill_col(todo):
    """Add COL+LPP to cities that have none (incl. freshly-added cities)."""
    done = 0; examples = []
    for f, d in todo:
        try:
            o = col_lpp(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: COL ERROR {ex}"); time.sleep(2); continue
        m = d["metrics"]; n = 0
        if o.get("col") is not None and 8 <= float(o["col"]) <= 175:
            m["cost_of_living_index"] = metric(round(float(o["col"]), 1), "index_numbeo_nyc100",
                ["numbeo"], "medium", notes="Numbeo Cost of Living Index, excl. rent, NYC=100"); n += 1
        if o.get("lpp") is not None and 0 <= float(o["lpp"]) <= 280:
            m["local_purchasing_power_index"] = metric(round(float(o["lpp"]), 1), "index_numbeo_nyc100",
                ["numbeo"], "medium", notes="Numbeo Local Purchasing Power Index, NYC=100"); n += 1
        if n:
            json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
            done += 1
            if len(examples) < 4: examples.append(d["city"])
            logln(f"  {d['id']}: COL {o.get('col')} LPP {o.get('lpp')}")
        else:
            logln(f"  {d['id']}: no Numbeo COL — skipped")
        time.sleep(0.6)
    return done, examples

def fill_rents(todo):
    done = 0; examples = []
    for f, d in todo:
        try:
            o = rents(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: RENT ERROR {ex}"); time.sleep(2); continue
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
            done += 1
            if len(examples) < 4: examples.append(d["city"])
            logln(f"  {d['id']}: rent1 {r1} rent3 {r3}")
        else:
            logln(f"  {d['id']}: no rent data — skipped")
        time.sleep(0.6)
    return done, examples

def fill_air(todo):
    done = 0; examples = []
    for f, d in todo:
        try:
            v = air_pm25(d["city"], d["country"])
        except Exception as ex:
            logln(f"  {d['id']}: AIR ERROR {ex}"); time.sleep(2); continue
        if v is None or not (1 <= float(v) <= 300):
            logln(f"  {d['id']}: no PM2.5 — skipped"); time.sleep(0.4); continue
        d["metrics"]["air_quality_pm25_ugm3"] = metric(round(float(v), 1), "ugm3", ["web"], "medium",
            method="annual mean PM2.5 (WHO/IQAir/national monitoring)", notes="Annual mean PM2.5; WHO guideline is 5 µg/m³")
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        done += 1
        if len(examples) < 4: examples.append(d["city"])
        logln(f"  {d['id']}: PM2.5 {v}")
        time.sleep(0.4)
    return done, examples

def backfill_tax(cities):
    """Instant, no-API: copy a country's income-tax metrics to any of its cities that
    lack them (e.g. a freshly-added city in an already-covered country)."""
    by_country = {}
    for f, d in cities:
        by_country.setdefault(d["country"], []).append((f, d))
    copied = 0
    for country, lst in by_country.items():
        src = next((d for _, d in lst if "income_tax_effective_mid_pct" in d["metrics"]), None)
        if not src: continue
        keys = [k for k in src["metrics"] if k.startswith("income_tax_effective_")]
        for f, d in lst:
            if "income_tax_effective_mid_pct" not in d["metrics"]:
                for k in keys: d["metrics"][k] = dict(src["metrics"][k])
                json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
                copied += 1
    if copied: logln(f"-- tax backfill: copied country rates to {copied} city/cities --")

def main():
    batch = int(sys.argv[sys.argv.index("--batch")+1]) if "--batch" in sys.argv else 15
    cities = load_published_cities()
    backfill_tax(cities)
    cities = load_published_cities()  # reload after backfill
    # Two backlogs so freshly-added cities (which have only prices) flow in:
    #   1) need COL — cities with no cost_of_living_index (incl. new capitals)
    #   2) need rents — cities that have COL but no rents
    need_col = [(f, d) for f, d in cities if "cost_of_living_index" not in d.get("metrics", {})]
    need_rent = [(f, d) for f, d in cities
                 if "cost_of_living_index" in d.get("metrics", {}) and "rent_3bed_usd_month" not in d["metrics"]]
    need_air = [(f, d) for f, d in cities if "air_quality_pm25_ugm3" not in d.get("metrics", {})]
    if not need_col and not need_rent and not need_air:
        logln("nothing to enrich this cycle — all cities have COL + rents + air quality"); return
    gsc = gsc_opportunity_slugs()
    traffic = plausible_traffic_slugs()
    logln(f"=== daily-enhance: {len(need_col)} need COL, {len(need_rent)} need rents, {len(need_air)} need air ===")

    col_done, col_ex = (0, [])
    if need_col:
        todo = prioritise(need_col, gsc, traffic)[:batch]
        logln(f"-- COL phase: {len(todo)} cities --")
        col_done, col_ex = fill_col(todo)
    rent_done, rent_ex = (0, [])
    if need_rent:
        todo = prioritise(need_rent, gsc, traffic)[:batch]
        logln(f"-- rents phase: {len(todo)} cities --")
        rent_done, rent_ex = fill_rents(todo)
    air_done, air_ex = (0, [])
    if need_air:
        todo = prioritise(need_air, gsc, traffic)[:batch]
        logln(f"-- air-quality phase: {len(todo)} cities --")
        air_done, air_ex = fill_air(todo)

    logln(f"=== DONE: +COL {col_done} (of {len(need_col)}), +rents {rent_done} (of {len(need_rent)}), "
          f"+air {air_done} (of {len(need_air)}) ===")
    parts = []
    if col_done: parts.append(f"cost-of-living for {col_done} cities ({', '.join(col_ex)})")
    if rent_done: parts.append(f"rents for {rent_done} cities ({', '.join(rent_ex)})")
    if air_done: parts.append(f"air quality for {air_done} cities ({', '.join(air_ex)})")
    if parts:
        notify("🏙️ TrendingCities daily: added " + "; ".join(parts)
               + f". Backlog: {len(need_col)-col_done} COL, {len(need_rent)-rent_done} rents, {len(need_air)-air_done} air.")

if __name__ == "__main__":
    main()
