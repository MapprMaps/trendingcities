# TrendingCities — Expansion & Relevance Plan
**Author:** Hugo (TrendingCities Desk) · **Date:** 2026-06-03 · for Andreas

---

## 1. Where we actually stand (no spin)

| Thing | Reality today |
|---|---|
| Places | **394** (333 cities + 61 districts), **74 countries** |
| Data dimensions | **One.** Home prices (1/2/3-bed median USD). Every other schema field — cost-of-living, income, rent, climate, safety, jobs — is **empty across all 394 records.** |
| Photos | 292/394 have a hero. The 102 gaps are **mostly real cities** (96 cities vs 6 districts) — your "it's the districts" hunch was only ~6% right. |
| Airports | **5/394** enriched. The "Getting there" card works but was never run at scale. |
| Maps / coords | 394/394. Good. |
| Traffic | **51 visitors / 238 pageviews in 30 days.** That's a brand-new site pre-indexing, not a failure — but it means we're building for the future, not defending existing rankings. |

**One-line summary:** we have a wide, well-engineered skeleton (clean schema, per-metric provenance, PR pipeline, API, maps, photos) wrapped around a **single thin layer of data.** The plumbing is excellent; the water is shallow.

## 2. The competitive reality (why this matters now)

- **Numbeo** — 9,000+ cities, daily crowdsourced updates, but now **charges $260/mo** for its estimator and the data is user-submitted (noisy).
- **WhereNext** (getwherenext.com) — this is the one to study. **Free, 380 cities, 95 countries, institutional data** (World Bank / OECD / Eurostat), **14 cost categories**, plus budget builder, salary calculator, expat-tax comparison, visa checker, **CC BY 4.0 + API + CSV.** That is *almost exactly the product TrendingCities is turning into* — and they're already there on depth. We match them on place-count and beat nobody on depth yet.

**Takeaway:** we don't win by out-counting Numbeo's 9,000 cities. We win by being the **cleanest, best-attributed, openly-licensed, affordability-first** city-economics dataset — and by actually shipping the depth WhereNext already has.

## 3. The freshness moat (the single most important strategic point)

Google's **March + May 2026 core updates gutted thin programmatic SEO** — template/AI pages with no real per-page data lost 60–90%. What survives: pages built on **unique, structured, *dated* data**, with a **verifiable "last updated"** tied to the source.

We already designed for this. The schema's per-metric `value / source / as_of / confidence` is **exactly the moat the 2026 algorithm rewards** — but only if we do two things we haven't:
1. **Actually fill the metrics** (right now there's almost nothing to be fresh *about*).
2. **Actually render the source + "last updated"** on every page (it's in the data, it's invisible on the site).

This is why the "boring" rendering task is not boring — it's the difference between surviving the next core update and not.

## 4. What to add — data layers, in priority order

Following your 2026-06-01 call:

1. **Cost-of-living index + median household income** → derive the **headline affordability metric**: *"years of median income to buy a 3-bed"* and *"local purchasing power."* This is the highest-value layer — it turns raw prices into the thing people actually search ("can I afford to live in X"). **Felix sources; I derive the ratios build-time (no research needed for the computed metrics).**
2. **Rent (1/2/3-bed)** → derive **price-to-rent ratio** (buy-vs-rent signal). Felix sources rent; I compute the ratio.
3. **Climate comfort, safety, air quality, job growth / unemployment** — the "should I move here" signals.
4. **Photos** — fill the 102 gaps (re-run, corpus-dependent; ~6 are districts).
5. **Per-metric source + "last updated" rendering** — already in schema, pure front-end. *Listed last in your priority but I'd ship it FIRST* (see §6) because it's the freshness moat and it's free.

No schema changes are needed for layers 1–3 — every key already exists in the registry. This is purely an ingestion + rendering exercise.

## 5. How to add — pipeline & division of labor (unchanged, just scaled)

```
Felix (research fan-out, per country/month)
   → emits incoming/{country}-{YYYY-MM}.json
      → I ingest idempotently → QC validate → human-gate borderline → merge → auto-deploy
```

- **Felix is the throughput bottleneck for layers 1–3.** I can't fix that by working harder; I *can* make sure the moment his data lands, it ships — by pre-building the ingestion + rendering ahead of the data.
- **Computed metrics are mine, need no research:** affordability ratio, price-to-rent, purchasing power — formulas over Felix's inputs, generated at build time.
- **Every new metric multiplies legitimate, differentiated pages:** new ranking pages + new compare dimensions + new city-page sections. This is the *good* kind of programmatic SEO (real unique data per page), not the kind Google punishes.

## 6. When — sequencing & cadence

**Now (this week, needs NO new data from Felix — pure leverage):**
- **A. Render per-metric source + "last updated" everywhere.** The freshness moat. Front-end only.
- **B. Re-run photos** for the 102 gaps (idempotent, ~20 min, near-free).
- **C. Run airports for all 394** (only 5 done). Easy win + dofollow cross-links to AirportRoutes (cross-property SEO).
- **D. Build the rendering + ingestion for the cost-of-living/income layer *now*, against sample data**, so it's plug-and-play when Felix delivers.

**As Felix delivers (rolling):**
- Ingest cost-of-living + income → ship the **affordability metric + ranking pages + an "Can I afford it?" calculator.**
- Then rent → **buy-vs-rent calculator + price-to-rent ranking.**
- Then climate / safety / jobs → "best places to move" rankings.

**Ongoing (the relevance engine):**
- **Monthly refresh cycle:** Felix research → my ingest → auto-deploy. Every record gets a dated refresh; records older than ~6–12 months get flagged stale. *This recurring cycle IS what keeps the site relevant over time* — freshness isn't a one-off, it's a cron.

## 7. Keeping it relevant over time (the brand promise)

The site is called **Trending**Cities — and **nothing on it currently trends.** That's the biggest gap between name and product. To fix it:

- **Month-over-month deltas** on every metric (price up/down vs last month), once we have ≥2 monthly snapshots. The schema's `as_of` already timestamps each — we just need to retain history.
- **"Fastest rising / falling" ranking pages** + a **/trends** hub. This is unique, genuinely fresh, perfectly on-brand, and the kind of "current-events" data signal that reads as alive to both users and Google.
- **Tools** (WhereNext parity + our affordability angle): affordability calculator, buy-vs-rent, cost-of-living compare. Tools earn backlinks and dwell time that static pages don't.
- **Optional later:** short, *data-grounded* "State of {city}" briefs — only if every sentence is backed by a real number. No thin AI filler; that's a core-update death wish.

## 8. Honest risks

- **Don't ship thin pages.** Every new page must carry unique data or it drags the whole domain down post-2026-updates.
- **Quality > quantity.** One wrong income figure burns trust we can't easily rebuild. Keep the human gate on borderline/low-confidence.
- **Felix is the gating dependency** for layers 1–3. The plan above front-loads everything that *doesn't* depend on him so we're never idle waiting.
- **WhereNext exists and is ahead on depth.** We need a sharp wedge — I'd make it **affordability-against-income + trends-over-time + open API**, not "another cost-of-living table."

## 9. My recommendation (if you want one decision)

Greenlight the **"Now" block (A–D)** this week — it's all within my scope, needs nothing from Felix, and lays the freshness + ingestion groundwork. In parallel, **ping Felix to start the cost-of-living + income fan-out**, because that's the long-pole and the single highest-value layer. Everything else sequences off those two.
