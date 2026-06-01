import type { APIRoute } from 'astro';
import { countries } from '../../lib/data';
import { apiJson, API_META, SITE } from '../../lib/api';

export const GET: APIRoute = () =>
  apiJson({
    meta: { ...API_META, endpoint: '/v1/countries.json', count: countries.length },
    countries: countries.map((c) => ({
      country: c.country,
      country_slug: c.countrySlug,
      page_url: `${SITE}/country/${c.countrySlug}/`,
      city_count: c.count,
      median_prices_usd: { one_bed: c.one, two_bed: c.two, three_bed: c.three },
    })),
  });
