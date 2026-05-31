#!/usr/bin/env python3
"""Backfill coordinates for every city record via Nominatim (OSM).
Writes coordinates{lat,lng} into each record; flags low-confidence/no-result
for human review. Idempotent: skips records that already have coordinates.
Polite: ~1 req/sec, custom UA, OSM attribution applies."""
import json, glob, time, urllib.parse, urllib.request, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UA = "trendingcities-geocode/1.0 (admin@trendingcities.com)"
FLAG_BELOW = 0.40  # Nominatim importance below this → flag for review

def geocode(query):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {"q": query, "format": "json", "limit": 1, "addressdetails": 0})
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=20).read())
    except Exception as e:
        return None
    if not d:
        return None
    return {"lat": round(float(d[0]["lat"]), 5), "lng": round(float(d[0]["lon"]), 5),
            "importance": round(float(d[0].get("importance", 0)), 3),
            "display": d[0].get("display_name", "")}

def main():
    files = sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True))
    flagged, done, skipped = [], 0, 0
    log = open("/tmp/tc_geocode.log", "w")
    for i, f in enumerate(files):
        rec = json.load(open(f))
        if rec.get("coordinates"):
            skipped += 1; continue
        # query: strip parens inline → "City Sub, Country"
        q = rec["city"].replace("(", "").replace(")", "") + ", " + rec["country"]
        g = geocode(q)
        if g:
            rec["coordinates"] = {"lat": g["lat"], "lng": g["lng"]}
            json.dump(rec, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n") if not open(f).read().endswith("\n") else None
            done += 1
            if g["importance"] < FLAG_BELOW:
                flagged.append({"city": rec["city"], "country": rec["country"], "coords": rec["coordinates"], "importance": g["importance"], "matched": g["display"][:70]})
            print(f"[{i+1}/{len(files)}] {rec['city']}, {rec['country']} -> {g['lat']},{g['lng']} (imp {g['importance']})", file=log, flush=True)
        else:
            flagged.append({"city": rec["city"], "country": rec["country"], "coords": None, "importance": 0, "matched": "NO RESULT"})
            print(f"[{i+1}/{len(files)}] {rec['city']}, {rec['country']} -> NO RESULT", file=log, flush=True)
        time.sleep(1.1)
    json.dump(flagged, open(os.path.join(ROOT, "scripts/geocode-flagged.json"), "w"), indent=2, ensure_ascii=False)
    print(f"DONE: geocoded={done} skipped={skipped} flagged={len(flagged)}", file=log, flush=True)
    print(f"DONE: geocoded={done} skipped={skipped} flagged={len(flagged)}")

if __name__ == "__main__":
    main()
