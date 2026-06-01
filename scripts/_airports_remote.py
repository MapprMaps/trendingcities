# Runs ON django-airportroutes inside `manage.py shell`.
# Reads /tmp/tc_coords.json [{slug,lat,lng}], writes /tmp/tc_air_out.json
# {slug: [{iata,icao,name,distance_km,destinations,airlines,type,url}]}.
#
# Picks the airports a traveller to this city would actually use:
#   - pool = scheduled-service real airports within RADIUS_KM
#   - rank: large_airport tier first, then medium, then by distance (so a city's
#     commercial hubs win over a nearby general-aviation field like Teterboro)
#   - a medium_airport must clear MIN_MED_DEST scheduled destinations to count
#     (drops GA/charter strips that carry a scheduled_service flag)
#   - if nothing qualifies (remote town, only tiny fields), fall back to the
#     single nearest scheduled airport so the card is never wrongly empty
import json
from core.models import Airport, FlightRoute
from django.contrib.gis.geos import Point
from django.contrib.gis.db.models.functions import Distance

REAL_TYPES = ["large_airport", "medium_airport"]
RADIUS_KM = 200
MIN_MED_DEST = 12  # a medium airport needs this many scheduled destinations to qualify
TYPE_RANK = {"large_airport": 0, "medium_airport": 1}

def counts(a):
    fr = FlightRoute.objects.filter(departure_airport=a, is_active=True)
    return (fr.values("destination_icao").distinct().count(),
            fr.values("operator_icao").distinct().count())

coords = json.load(open("/tmp/tc_coords.json"))
out = {}
for c in coords:
    pt = Point(c["lng"], c["lat"], srid=4326)
    pool = (Airport.objects
            .filter(scheduled_service=True, type__in=REAL_TYPES, location__isnull=False)
            .annotate(d=Distance("location", pt)).order_by("d")[:18])
    cand = []      # qualifying
    nearest = None  # fallback
    for a in pool:
        if not a.icao or a.d.km > RADIUS_KM:
            continue
        dests, ops = counts(a)
        row = {
            "iata": a.iata or "", "icao": a.icao, "name": a.name, "type": a.type,
            "distance_km": round(a.d.km), "destinations": dests, "airlines": ops,
            "url": f"https://www.airportroutes.com/airports/{a.icao}/",
        }
        if nearest is None and (dests or ops):
            nearest = row
        if a.type == "large_airport" or dests >= MIN_MED_DEST:
            cand.append(row)
    cand.sort(key=lambda r: (TYPE_RANK.get(r["type"], 9), r["distance_km"]))
    rows = cand[:3] if cand else ([nearest] if nearest else [])
    out[c["slug"]] = rows

json.dump(out, open("/tmp/tc_air_out.json", "w"))
print(f"WROTE {len(out)} cities")
