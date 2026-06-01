// Shared serialisers for the public TrendingCities API (api.trendingcities.com/v1).
// Generated from the SAME data layer as the site, so the API never drifts.
import { type City, vsMedian, DATA_VERSION, DATA_UPDATED } from './data';

export const SITE = 'https://www.trendingcities.com';
export const ATTRIBUTION = 'Data by TrendingCities (https://www.trendingcities.com) - CC BY 4.0; attribution required.';

/** One city/district as a stable public API object. */
export function apiCity(c: City) {
  return {
    id: c.slug, // "germany/berlin" or "germany/berlin/mitte"
    city: c.city,
    country: c.country,
    country_code: c.countryCode,
    is_district: c.isDistrict,
    parent: c.parentSlug ?? null,
    page_url: `${SITE}${c.url}`,
    coordinates: typeof c.lat === 'number' ? { lat: c.lat, lng: c.lng } : null,
    prices_usd: { one_bed: c.one, two_bed: c.two, three_bed: c.three },
    vs_global_median_pct: {
      one_bed: vsMedian(c.one, 'one'),
      two_bed: vsMedian(c.two, 'two'),
      three_bed: vsMedian(c.three, 'three'),
    },
    as_of: c.asOf,
    sources: c.sources,
    airports: c.airports ?? [],
    photo: c.hero
      ? {
          url: c.hero.url,
          photographer: c.hero.photographer || null,
          source: c.hero.source,
          source_url: c.hero.ss_url || null,
          license: c.hero.license || null,
        }
      : null,
  };
}

/** Standard JSON response (headers also enforced via public/_headers for static serving). */
export function apiJson(payload: unknown) {
  return new Response(JSON.stringify(payload), {
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=3600',
      'X-Attribution': ATTRIBUTION,
    },
  });
}

export const API_META = {
  name: 'TrendingCities API',
  version: 'v1',
  dataset_version: DATA_VERSION,
  data_updated: DATA_UPDATED,
  base_url: 'https://api.trendingcities.com/v1',
  license: 'CC BY 4.0',
  attribution: ATTRIBUTION,
  docs: 'https://api.trendingcities.com/v1/',
};
