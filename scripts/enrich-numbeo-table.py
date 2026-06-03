#!/usr/bin/env python3
"""Populate cost_of_living_index + local_purchasing_power_index for all top-level
cities from Numbeo's published Cost-of-Living rankings table (one page, ~479
cities, real data, NYC=100). This is the reliable, honest, scalable source —
no LLM guessing. Cities not on Numbeo's list are left empty (honest absence).

Matching: exact (city, country) → same-country prefix → unique city-only.
Overwrites COL/LPP (Numbeo is authoritative) but preserves all other metrics
(e.g. the flagship cities' USD rents + price_to_rent).

Run: python3 scripts/enrich-numbeo-table.py   (expects /tmp/numbeo_rankings.html)
"""
import re, json, glob, os, unicodedata, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AS_OF = "2026-06"
HTML = sys.argv[1] if len(sys.argv) > 1 else "/tmp/numbeo_rankings.html"

def norm(s):
    s = unicodedata.normalize('NFKD', s).encode('ascii', 'ignore').decode().lower()
    return re.sub(r'[^a-z0-9]', '', s)

# Known transliteration / endonym aliases (our name -> numbeo name), normalized.
ALIAS = {
    'kyiv': 'kiev', 'odesa': 'odessa', 'astana': 'nursultan', 'seville': 'sevilla',
    'marrakesh': 'marrakech', 'thehague': 'denhaag', 'krakow': 'cracow',
}

def aliases(name):
    """Normalized name variants: full, part-before-paren, part-inside-paren, + ALIAS."""
    out = set()
    base = name.strip()
    inside = re.findall(r'\(([^)]+)\)', base)
    before = re.sub(r'\s*\([^)]*\)', '', base)
    for cand in [base, before] + inside:
        n = norm(cand)
        if n:
            out.add(n)
            if n in ALIAS: out.add(ALIAS[n])
    return out

def parse_table(path):
    html = open(path).read()
    cells = re.findall(r'<td class="cityOrCountryInIndicesTable">([^<]+)</td>((?:\s*<td[^>]*>[^<]*</td>){6})', html)
    by_pair, by_city = {}, {}
    for name, block in cells:
        vals = [float(x) for x in re.findall(r'>([\d.]+)</td>', block)]
        if len(vals) < 6: continue
        parts = [p.strip() for p in name.split(',')]
        city, country = parts[0], parts[-1]
        rec = {"col": vals[0], "lpp": vals[5]}  # col 0 = Cost of Living Index, col 5 = LPP
        nco = norm(country)
        for a in aliases(city):
            by_pair[(a, nco)] = rec
            by_city.setdefault(a, []).append((nco, rec))
    return by_pair, by_city

def match(d, by_pair, by_city):
    nco = norm(d['country'])
    ours = aliases(d['city'])
    for a in ours:
        if (a, nco) in by_pair: return by_pair[(a, nco)]
    # same-country prefix (Patra/Patras, Tel Aviv/Tel Aviv-Yafo)
    for a in ours:
        for c, lst in by_city.items():
            for cc, r in lst:
                if cc == nco and len(a) >= 5 and (c.startswith(a) or a.startswith(c)) and abs(len(c)-len(a)) <= 5:
                    return r
    for a in ours:  # unique city name globally
        if a in by_city and len({cc for cc, _ in by_city[a]}) == 1:
            return by_city[a][0][1]
    return None

def metric(value, notes):
    return {"value": round(value, 1), "unit": "index_numbeo_nyc100", "as_of": AS_OF,
            "sources": ["numbeo"], "confidence": "medium", "notes": notes}

def main():
    by_pair, by_city = parse_table(HTML)
    print(f"numbeo table: {len(by_pair)} city/country entries")
    placed = miss = 0; misses = []
    for f in sorted(glob.glob(os.path.join(ROOT, "data/cities/**/*.json"), recursive=True)):
        d = json.load(open(f))
        if d.get('provenance', {}).get('status') != 'published': continue
        if d['id'].count('/') != 1: continue
        r = match(d, by_pair, by_city)
        if not r:
            miss += 1; misses.append(f"{d['city']}, {d['country']}"); continue
        m = d.setdefault('metrics', {})
        m['cost_of_living_index'] = metric(r['col'], "Numbeo Cost of Living Index, excl. rent, NYC=100")
        m['local_purchasing_power_index'] = metric(r['lpp'], "Numbeo Local Purchasing Power Index, NYC=100")
        json.dump(d, open(f, "w"), indent=2, ensure_ascii=False); open(f, "a").write("\n")
        placed += 1
    print(f"PLACED: {placed} cities got COL+LPP | MISS: {miss} (not on Numbeo list)")
    print("misses:", ", ".join(misses))

if __name__ == "__main__":
    main()
