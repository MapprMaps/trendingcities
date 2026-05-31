#!/usr/bin/env python3
"""One-shot migration: flat prices.json -> per-city record files under
data/cities/{country-slug}/{city-slug}.json, conforming to
hermes-chief/trendingcities/city-record.schema.json.

The file PATH is the source of truth for slugs/URLs (country dir + city file),
so the Astro data layer derives id/slug from the path and collisions are
resolved here at write time (append -2, -3…).
"""
import json, re, os, sys, unicodedata
import pycountry

SRC = os.path.join(os.path.dirname(__file__), "..", "src", "data", "prices.json")
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "cities")

CC_OVERRIDE = {
    "Czech Republic": "CZ", "Russia": "RU", "Taiwan": "TW", "North Macedonia": "MK",
    "Bosnia and Herzegovina": "BA", "Moldova": "MD", "Vietnam": "VN", "Turkey": "TR",
    "United Kingdom": "GB", "United States": "US", "Hong Kong": "HK", "Macau": "MO",
    "Puerto Rico": "PR", "South Africa": "ZA", "South Korea": "KR",
}

def country_code(name):
    if name in CC_OVERRIDE:
        return CC_OVERRIDE[name]
    try:
        return pycountry.countries.lookup(name).alpha_2
    except LookupError:
        try:
            return pycountry.countries.search_fuzzy(name)[0].alpha_2
        except Exception:
            return "ZZ"

def slugify(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace("&", "and")
    s = re.sub(r"[()'’.]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def main():
    rows = json.load(open(SRC))
    seen = set()
    written = 0
    for r in rows:
        cs = slugify(r["country"])
        base = slugify(r["city"])
        cslug, n = base, 2
        while f"{cs}/{cslug}" in seen:
            cslug = f"{base}-{n}"; n += 1
        seen.add(f"{cs}/{cslug}")
        cc = country_code(r["country"])
        def metric(v):
            return {
                "value": v, "unit": "USD", "as_of": "2026-05",
                "sources": ["globalpropertyguide", "numbeo", "web"],
                "method": "cross-source-median", "confidence": "medium",
            }
        rec = {
            "schema_version": "1.0",
            "id": f"{cs}/{cslug}",
            "city": r["city"],
            "country": r["country"],
            "country_code": cc,
            "metrics": {
                "home_price_1bed_usd": metric(r["one_bed_usd"]),
                "home_price_2bed_usd": metric(r["two_bed_usd"]),
                "home_price_3bed_usd": metric(r["three_bed_usd"]),
            },
            "provenance": {
                "compiled_by": "starter-2026.1",
                "compiled_at": "2026-05-31",
                "status": "published",
            },
        }
        d = os.path.join(OUT, cs)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{cslug}.json"), "w") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)
        written += 1
    print(f"wrote {written} city record files under data/cities/")
    zz = [c for c in seen]  # noqa
    # report any unresolved country codes
    bad = sorted(set(r["country"] for r in rows if country_code(r["country"]) == "ZZ"))
    if bad:
        print("UNRESOLVED country codes:", bad)

if __name__ == "__main__":
    main()
