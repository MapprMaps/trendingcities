#!/usr/bin/env python3
"""Correction pass: re-geocode flagged records using the PARENT city
(strip the parenthetical sub-area), which geocodes reliably. Sub-areas of the
same city then cluster correctly instead of matching random POIs."""
import json, glob, re, time, os, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "trendingcities-geocode/1.0 (admin@trendingcities.com)"

def geocode(q):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({"q": q, "format": "json", "limit": 1})
    try:
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read())
    except Exception:
        return None
    return {"lat": round(float(d[0]["lat"]), 5), "lng": round(float(d[0]["lon"]), 5), "imp": round(float(d[0].get("importance", 0)), 3)} if d else None

def parent_city(city):
    # "Paris (16eme)" -> "Paris"; "Dubai (all)" -> "Dubai"; "Cambodia (combined)" -> "Cambodia"
    base = re.sub(r"\s*\(.*?\)\s*", " ", city).strip()
    return base or city

flag = json.load(open(os.path.join(ROOT, "scripts/geocode-flagged.json")))
# index files by (city,country)
idx = {}
for f in glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True):
    d = json.load(open(f)); idx[(d["city"], d["country"])] = f
fixed, still = 0, []
for x in flag:
    key = (x["city"], x["country"]); f = idx.get(key)
    if not f: continue
    base = parent_city(x["city"])
    g = geocode(f"{base}, {x['country']}") or geocode(base) or geocode(x["country"])
    if g:
        rec = json.load(open(f)); rec["coordinates"] = {"lat": g["lat"], "lng": g["lng"]}
        json.dump(rec, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        fixed += 1
        print(f"  fixed {x['city']}, {x['country']} via '{base}' -> {g['lat']},{g['lng']} (imp {g['imp']})", flush=True)
    else:
        still.append(f"{x['city']}, {x['country']}")
    time.sleep(1.1)
print(f"DONE fix: fixed={fixed} still_missing={len(still)}")
if still: print("still missing:", still)
