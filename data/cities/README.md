# TrendingCities — city dataset

This folder is the **open dataset** behind [www.trendingcities.com](https://www.trendingcities.com/). One JSON file per city:

```
data/cities/{country-slug}/{city-slug}.json
```

The file path is the city's identity — it drives the URL `/city/{country-slug}/{city-slug}/`. Each file is one record conforming to the schema in `city-record.schema.json` (kept in the maintainers' notes; mirrored here on request).

## Record shape (v1)

```jsonc
{
  "schema_version": "1.0",
  "id": "japan/tokyo",
  "city": "Tokyo",
  "country": "Japan",
  "country_code": "JP",        // ISO 3166-1 alpha-2
  "metrics": {
    "home_price_1bed_usd": {
      "value": 363000,
      "unit": "USD",
      "as_of": "2026-05",       // when the figure is from (YYYY-MM)
      "sources": ["globalpropertyguide", "numbeo", "web"],
      "method": "cross-source-median",
      "confidence": "medium"    // high | medium | low
    },
    "home_price_2bed_usd": { "...": "..." },
    "home_price_3bed_usd": { "...": "..." }
  },
  "provenance": { "compiled_by": "...", "compiled_at": "2026-05-31", "status": "published" }
}
```

Only records with `provenance.status: "published"` are built into the live site.

## Contributing a price (community)

Two ways:
1. **On-site** — use the "Suggest an update" form on any city page. It opens a pull request for you (no GitHub account needed). *(Coming in Phase 3.)*
2. **Directly** — edit the city's JSON file and open a pull request. Put your figure in the relevant `home_price_*bed_usd.value`, set `as_of` to the month it reflects, and add a `notes` line with where it came from.

Every data PR is checked automatically (schema + plausibility) before a maintainer reviews it. Keep prices in **USD**, and remember 1-bed ≤ 2-bed ≤ 3-bed for the same city.

## Agent updates

Research agents submit monthly per-country updates as pull requests labeled `agent-update`, with full provenance (source + date + confidence). High-confidence updates that pass automated QC and stay within tolerance are merged automatically; anything unusual is held for human review.
