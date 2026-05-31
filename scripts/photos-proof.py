#!/usr/bin/env python3
"""8-city photo proof: SampleShots Discovery Engine (licensed Unsplash corpus,
bbox-filtered by each city's coords) -> vision model picks the best hero ->
store in the record's media field. Curation model swaps to Vertex Gemini for
the 400-run once that access is enabled."""
import json, os, re, math, subprocess, base64, urllib.request, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT = "sitemetrics-458214"
DE_URL = (f"https://global-discoveryengine.googleapis.com/v1/projects/{PROJECT}/locations/global/"
          "collections/default_collection/engines/pw-smart-photo-search-engine/servingConfigs/default_search:search")
SLUGS = ["portugal/lisbon", "japan/tokyo", "united-states/new-york", "australia/sydney",
         "germany/berlin-mitte", "united-arab-emirates/dubai", "mexico/mexico-city", "spain/barcelona"]

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
    # Pre-rank by the database's own popularity so the strongest shots lead.
    out.sort(key=lambda c: (c["popularity"], c["downloads"], c["likes"]), reverse=True)
    return out[:6]

def acceptable(city, country, cands):
    """OpenAI vision returns the SHORTLIST of acceptable heroes (0-based indices).
    Quality is the gate; popularity (already pre-ranked) breaks the tie afterwards."""
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
    req = urllib.request.Request("https://api.openai.com/v1/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=60).read())
        txt = r["choices"][0]["message"]["content"]
        nums = [int(n) for n in re.findall(r"\d+", txt)]
        return [n-1 for n in nums if 1 <= n <= len(cands)]
    except Exception as e:
        print("   vision err:", str(e)[:80]); return [0]  # fall back to most-popular

def main():
    token = de_token()
    files = {}
    for f in glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True):
        d = json.load(open(f)); files[d["id"]] = f
    for slug in SLUGS:
        f = files.get(slug)
        if not f: print(f"  {slug}: NOT FOUND"); continue
        rec = json.load(open(f))
        co = rec.get("coordinates")
        if not co: print(f"  {slug}: no coords"); continue
        cands = candidates(token, rec["city"], rec["country"], co["lat"], co["lng"])
        if not cands: print(f"  {slug}: 0 candidates"); continue
        ok = acceptable(rec["city"], rec["country"], cands)
        if not ok: print(f"  {slug}: vision found none good ({len(cands)} cands)"); continue
        # Among the vision-approved shots, take the most popular (cands are pre-sorted by popularity).
        idx = min(ok)
        ch = cands[idx]
        rec["media"] = {"photo_ids": [ch["id"]] if ch["id"] else [],
            "hero": {"url": re.sub(r"w=\d+", "w=1600", ch["image_url"]),
                     "title": ch["title"], "photographer": ch["photographer"],
                     "username": ch.get("username", ""), "ss_url": ch.get("ss_url", ""),
                     "source": ch["source"], "license": ch["license"]}}
        json.dump(rec, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        print(f"  {slug}: {len(ok)} ok of {len(cands)} -> #{idx+1} (pop {ch['popularity']:.3f}, {ch['downloads']}dl) "
              f"— {ch['title'][:38]} (by {ch['photographer'] or ch['source']})")
    print("DONE")

if __name__ == "__main__":
    main()
