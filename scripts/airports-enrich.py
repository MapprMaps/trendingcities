#!/usr/bin/env python3
"""Enrich city records with nearest airports (scheduled service) from AirportRoutes.
Build-time enrichment: computes nearest 3 real airports per city via the AirportRoutes
PostGIS DB (over SSH), writes them into each record's `airports` field. Refresh monthly.
Usage: python3 scripts/airports-enrich.py [slug ...]   (no args = all published records)
"""
import json, os, glob, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = "root@django-airportroutes"
REMOTE = os.path.join(ROOT, "scripts/_airports_remote.py")

def main():
    want = set(sys.argv[1:])
    recs = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get("provenance", {}).get("status") != "published":
            continue
        co = d.get("coordinates")
        if not co or co.get("lat") is None:
            continue
        if want and d["id"] not in want:
            continue
        recs[d["id"]] = (f, d, co)
    if not recs:
        print("no matching records"); return
    coords = [{"slug": s, "lat": co["lat"], "lng": co["lng"]} for s, (_, _, co) in recs.items()]
    print(f"querying AirportRoutes for {len(coords)} cities…")

    # ship coords + script, run inside Django shell, pull results
    subprocess.run(["ssh", HOST, "cat > /tmp/tc_coords.json"], input=json.dumps(coords).encode(), check=True)
    subprocess.run(["scp", "-q", REMOTE, f"{HOST}:/tmp/tc_air.py"], check=True)
    r = subprocess.run(["ssh", HOST,
        "cd /root/airportroutes && source venv/bin/activate 2>/dev/null && "
        "python manage.py shell -c \"exec(open('/tmp/tc_air.py').read())\" 2>/dev/null && "
        "cat /tmp/tc_air_out.json"], capture_output=True, text=True)
    # the script prints "WROTE n" then the file is cat'd; grab the JSON object
    txt = r.stdout
    start = txt.find("{", txt.find("WROTE") if "WROTE" in txt else 0)
    data = json.loads(txt[start:]) if start >= 0 else json.loads(txt)

    placed = 0; empty = 0
    for slug, (f, d, _) in recs.items():
        airports = data.get(slug, [])
        if airports:
            d["airports"] = airports
            json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
            placed += 1
            top = airports[0]
            print(f"  {slug}: {len(airports)} -> {top['iata'] or top['icao']} {top['distance_km']}km, "
                  f"{top['destinations']} dests / {top['airlines']} airlines")
        else:
            empty += 1; print(f"  {slug}: no scheduled airport nearby")
    print(f"DONE: {placed} enriched, {empty} without nearby airport")

if __name__ == "__main__":
    main()
