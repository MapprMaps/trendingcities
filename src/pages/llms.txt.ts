import type { APIRoute } from 'astro';
import { CITY_COUNT, COUNTRY_COUNT, medians, DATA_UPDATED, DATA_VERSION, mostExpensive3, mostAffordable1 } from '../lib/data';
import { usd } from '../lib/format';

export const GET: APIRoute = () => {
  const exp = mostExpensive3.slice(0, 5).map((c) => `  - ${c.city}, ${c.country} (3-bed ${usd(c.three)}): https://www.trendingcities.com${c.url}`).join('\n');
  const aff = mostAffordable1.slice(0, 5).map((c) => `  - ${c.city}, ${c.country} (1-bed ${usd(c.one)}): https://www.trendingcities.com${c.url}`).join('\n');
  const body = `# TrendingCities

> Compare median home prices across ${CITY_COUNT} cities in ${COUNTRY_COUNT} countries. Median 1-bed ${usd(medians.one)}, 2-bed ${usd(medians.two)}, 3-bed ${usd(medians.three)}. Starter dataset v${DATA_VERSION} (${DATA_UPDATED}) — directional median home-purchase prices in USD; full provenance in progress.

## Key pages
- Homepage: https://www.trendingcities.com/
- City profiles: https://www.trendingcities.com/city/{country-slug}/{city-slug}/ — 1/2/3-bed median prices and affordability vs the global median.
- Rankings:
  - Most expensive (3-bed): https://www.trendingcities.com/rankings/most-expensive-3-bed/
  - Most affordable (1-bed): https://www.trendingcities.com/rankings/most-affordable-1-bed/
  - Best 2-bed under $250k: https://www.trendingcities.com/rankings/best-2-bed-under-250k/
  - Country comparison: https://www.trendingcities.com/rankings/country-comparison/
- Compare two cities: https://www.trendingcities.com/compare/
- Data & methodology: https://www.trendingcities.com/data/

## Data notes
- Each city has median purchase prices (USD) for 1, 2 and 3-bedroom homes.
- "vs median" compares a city to the global dataset median for that bedroom type.
- Directional only — not a valuation of any specific property. Coverage per country varies.
- Roadmap: cost of living, income, rent, climate, safety, jobs, and photography.

## Most expensive (3-bed)
${exp}

## Most affordable (1-bed)
${aff}
`;
  return new Response(body, { headers: { 'Content-Type': 'text/plain; charset=utf-8' } });
};
