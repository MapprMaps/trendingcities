#!/usr/bin/env python3
"""Full 400-city hero curation: for every published city record with coordinates,
query the SampleShots Discovery Engine (licensed corpus, bbox-filtered), let
gpt-4o-mini vision gate for an acceptable skyline, then pick the most-POPULAR
of the approved shots. Resumable: skips records that already have a media.hero.
Run: source ~/.secrets && OPENAI_API_KEY=$OPENAI_API_KEY python3 scripts/photos-all.py
"""
import json, os, re, math, subprocess, urllib.request, glob, time, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "sitemetrics-458214"
DE_URL = (f"https://global-discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/"
          "collections/default_collection/engines/pw-smart-photo-search-engine/servingConfigs/default_search:search")
LOG = os.path.join(ROOT, "photos-all.log")

def logln(msg):
    line = msg if isinstance(msg, str) else str(msg)
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")

def de_token():
    return subprocess.run(["gcloud", "auth", "print-access-token"], capture_output=True, text=True).stdout.strip()

def post(url, token, body):
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=40).read())

def bbox(lat, lng, r=25):
    dlat = r/111.32; dlng = r/(111.32*math.cos(math.radians(lat)))
    return f"latitude >= {lat-dlat:.5f} AND latitude <= {lat+dlat:.5f} AND longitude >= {lng-dlng:.5f} AND longitude <= {lng+dlng:.5f}"

def candidates(token, city, country, lat, lng):
    r = post(DE_URL, token, {"query": f"{city} {country} skyline cityscape city center landmark",
        "pageSize": 8, "filter": bbox(lat, lng)})
    out = []
    for res in r.get("results", []):
        s = res.get("document", {}).get("structData", {}) or res.get("document", {}).get("derivedStructData", {})
        url = s.get("image_url")
        if url:
            out.append({"image_url": url, "title": s.get("title", ""), "source": s.get("source", ""),
                        "photographer": s.get("photographer_name", ""), "username": s.get("photographer_username", ""),
                        "ss_url": s.get("ss_photo_url", ""),
                        "license": s.get("license_name", ""), "id": s.get("photo_id") or s.get("source_id") or "",
                        "popularity": float(s.get("popularity_score") or 0), "downloads": int(s.get("downloads") or 0),
                        "likes": int(s.get("likes") or 0)})
    out.sort(key=lambda c: (c["popularity"], c["downloads"], c["likes"]), reverse=True)
    return out[:6]

def acceptable(city, country, cands):
    """Vision shortlist of acceptable heroes (0-based indices). Quality gate; popularity ranks after."""
    key = os.environ["OPENAI_API_KEY"]
    content = [{"type": "text", "text":
        f"These are candidate photos for the HERO image of the city page for {city}, {country}. "
        f"An ACCEPTABLE hero is a wide, daylight skyline or cityscape that clearly and recognisably shows {city}, "
        f"magazine/editorial quality — NOT a close-up of a single building, NOT a map, NOT an indoor or product shot, "
        f"NOT a night shot unless it's an iconic skyline. "
        f"Reply with the numbers (1-{len(cands)}) of ALL acceptable photos, comma-separated, or 0 if none are good. "
        f"List every one that would work — don't pick just one."}]
    for c in cands:
        thumb = re.sub(r"w=\d+", "w=420", c["image_url"])
        content.append({"type": "image_url", "image_url": {"url": thumb, "detail": "low"}})
    body = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": content}], "max_tokens": 24, "temperature": 0}
    for attempt in range(3):
        try:
            req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            r = json.loads(urllib.request.urlopen(req, timeout=60).read())
            txt = r["choices"][0]["message"]["content"]
            nums = [int(n) for n in re.findall(r"\d+", txt)]
            return [n-1 for n in nums if 1 <= n <= len(cands)]
        except Exception as e:
            if attempt == 2:
                logln(f"   vision err (giving up): {str(e)[:80]}"); return []
            time.sleep(3 * (attempt + 1))

def main():
    token = de_token()
    t0 = time.time()
    recs = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        try: d = json.load(open(f))
        except Exception: continue
        if d.get("provenance", {}).get("status") == "published":
            recs.append((f, d))
    total = len(recs)
    done = sum(1 for _, d in recs if d.get("media", {}).get("hero"))
    logln(f"=== 400-run start: {total} published records, {done} already have a hero, "
          f"{total-done} to process ===")
    placed = done; rejected = 0; nocoord = 0; errors = 0; processed = 0
    for f, rec in recs:
        if rec.get("media", {}).get("hero"):
            continue  # resumable: keep existing pick
        slug = rec.get("id", os.path.basename(f))
        co = rec.get("coordinates")
        if not co or co.get("lat") is None:
            nocoord += 1; logln(f"  [{slug}] no coords — skip"); continue
        processed += 1
        try:
            cands = candidates(token, rec["city"], rec["country"], co["lat"], co["lng"])
        except Exception as e:
            errors += 1; logln(f"  [{slug}] search err: {str(e)[:70]}")
            # token may have expired — refresh once and retry next loop
            token = de_token(); continue
        if not cands:
            rejected += 1; logln(f"  [{slug}] 0 candidates in bbox"); continue
        ok = acceptable(rec["city"], rec["country"], cands)
        if not ok:
            rejected += 1; logln(f"  [{slug}] vision rejected all {len(cands)}"); continue
        idx = min(ok)  # most-popular among approved (cands pre-sorted by popularity)
        ch = cands[idx]
        rec["media"] = {"photo_ids": [ch["id"]] if ch["id"] else [],
            "hero": {"url": re.sub(r"w=\d+", "w=1600", ch["image_url"]),
                     "title": ch["title"], "photographer": ch["photographer"],
                     "username": ch.get("username", ""), "ss_url": ch.get("ss_url", ""),
                     "source": ch["source"], "license": ch["license"]}}
        json.dump(rec, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        placed += 1
        if processed % 25 == 0:
            el = int(time.time() - t0)
            logln(f"  ... {processed} processed | {placed} placed, {rejected} rejected | {el}s elapsed")
    el = int(time.time() - t0)
    logln(f"=== DONE in {el}s: {placed}/{total} cities have a hero | "
          f"{rejected} no-good-photo | {nocoord} no-coords | {errors} search errors ===")

if __name__ == "__main__":
    main()
