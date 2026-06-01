#!/usr/bin/env python3
"""One-shot IA migration: resolve parent-city / district duplication.
- DROP artifacts whose parent/main-city already holds the data.
- RENAME the 3 artifacts that are a place's ONLY record (don't orphan a capital).
- NEST real districts under their parent: data/cities/{c}/{parent}/{district}.json,
  so the URL becomes /city/{c}/{parent}/{district}/ (was a flat sibling).
- EMIT public/_redirects: 301 every old flat district URL -> its new nested URL.
Idempotent-ish: safe to read first with --dry.
"""
import json, glob, os, sys, re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRY = "--dry" in sys.argv
CITIES = os.path.join(ROOT, "data/cities")

DROP = {  # parent / main-city already covers these
    "germany/munich-district-munich", "new-zealand/auckland-apartments",
    "turkey/istanbul-all", "united-arab-emirates/dubai-all",
    "iceland/iceland-all", "luxembourg/luxembourg-all",
}
RENAME = {  # artifact -> clean city slug (these are a place's only record)
    "united-arab-emirates/abu-dhabi-all": ("abu-dhabi", "Abu Dhabi"),
    "new-zealand/wellington-apartments": ("wellington", "Wellington"),
    "new-zealand/christchurch-townhouses": ("christchurch", "Christchurch"),
}
DROP_REDIRECT = {  # dropped URL -> where it should 301 (parent / main city)
    "germany/munich-district-munich": "germany/munich",
    "new-zealand/auckland-apartments": "new-zealand/auckland",
    "turkey/istanbul-all": "turkey/istanbul",
    "united-arab-emirates/dubai-all": "united-arab-emirates/dubai",
    "iceland/iceland-all": "iceland/reykjavik",
    "luxembourg/luxembourg-all": "luxembourg/luxembourg-city",
}

def load_all():
    recs = {}
    for f in sorted(glob.glob(os.path.join(CITIES, "**/*.json"), recursive=True)):
        d = json.load(open(f)); recs[d["id"]] = [f, d]
    return recs

def main():
    recs = load_all()
    log = []
    extra_redirects = []

    # 1. DROP
    for slug in sorted(DROP):
        if slug in recs:
            f = recs[slug][0]
            log.append(f"DROP   {slug}")
            if not DRY: os.remove(f)
            del recs[slug]
            tgt = DROP_REDIRECT.get(slug)
            if tgt:
                extra_redirects.append((f"/city/{slug}/", f"/city/{tgt}/"))

    # 2. RENAME (flat -> clean flat)
    for slug in sorted(RENAME):
        if slug not in recs: continue
        country = slug.split("/", 1)[0]
        newcity, newname = RENAME[slug]
        f, d = recs[slug]
        newid = f"{country}/{newcity}"
        newf = os.path.join(CITIES, country, newcity + ".json")
        d["id"] = newid
        d["city"] = newname
        log.append(f"RENAME {slug} -> {newid}  (city '{newname}')")
        if not DRY:
            json.dump(d, open(newf, "w"), indent=2, ensure_ascii=False); open(newf, "a").write("\n")
            os.remove(f)
        del recs[slug]
        recs[newid] = [newf, d]
        extra_redirects.append((f"/city/{slug}/", f"/city/{newid}/"))

    # 3. NEST districts. A record is a district if another record's citySlug is a
    #    prefix and it's "{parent}-{rest}". Parent must be a top-level (2-seg) record.
    slugs = set(recs.keys())
    def citySlugOf(s): return s.split("/", 1)[1]
    redirects = []
    moves = []
    for slug in sorted(slugs):
        country, cs = slug.split("/", 1)
        # find the longest parent whose citySlug is a prefix and exists
        best = None
        for p in slugs:
            if p == slug: continue
            pc, pcs = p.split("/", 1)
            if pc != country: continue
            if "/" in pcs: continue  # parent must be top-level
            if cs.startswith(pcs + "-"):
                if best is None or len(pcs) > len(best):
                    best = pcs
        if best:
            district = cs[len(best) + 1:]
            newid = f"{country}/{best}/{district}"
            newf = os.path.join(CITIES, country, best, district + ".json")
            moves.append((slug, newid, newf, recs[slug][0], recs[slug][1]))
            redirects.append((f"/city/{country}/{cs}/", f"/city/{country}/{best}/{district}/"))

    for slug, newid, newf, oldf, d in moves:
        d["id"] = newid
        log.append(f"NEST   {slug} -> {newid}")
        if not DRY:
            os.makedirs(os.path.dirname(newf), exist_ok=True)
            json.dump(d, open(newf, "w"), indent=2, ensure_ascii=False); open(newf, "a").write("\n")
            os.remove(oldf)

    # 4. redirects file
    redirects.extend(extra_redirects)
    redirects.sort()
    body = "# District IA migration — flat district URLs -> nested under parent (301)\n"
    body += "\n".join(f"{a} {b} 301" for a, b in redirects) + "\n"
    rpath = os.path.join(ROOT, "public/_redirects")
    if not DRY:
        # preserve any existing redirects, append ours (dedup)
        existing = ""
        if os.path.exists(rpath):
            existing = open(rpath).read()
        lines = [l for l in existing.splitlines() if l.strip() and "/city/" not in l]
        merged = ("\n".join(lines) + "\n" if lines else "") + body
        open(rpath, "w").write(merged)

    print("\n".join(log))
    print(f"\n{'(DRY) ' if DRY else ''}DROP={len(DROP)} RENAME={len(RENAME)} NEST={len(moves)} REDIRECTS={len(redirects)}")

if __name__ == "__main__":
    main()
