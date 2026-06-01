import type { APIRoute } from 'astro';
import { medians, CITY_COUNT, DISTRICT_COUNT, PLACE_COUNT, COUNTRY_COUNT } from '../../lib/data';
import { apiJson, API_META } from '../../lib/api';

export const GET: APIRoute = () =>
  apiJson({
    ...API_META,
    counts: { cities: CITY_COUNT, districts: DISTRICT_COUNT, places: PLACE_COUNT, countries: COUNTRY_COUNT },
    global_median_usd: { one_bed: medians.one, two_bed: medians.two, three_bed: medians.three },
    endpoints: [
      '/v1/meta.json',
      '/v1/cities.json',
      '/v1/city/{country}/{city}.json',
      '/v1/city/{country}/{city}/{district}.json',
      '/v1/countries.json',
      '/v1/rankings/{most-expensive-3-bed|most-affordable-1-bed|best-2-bed-under-250k}.json',
    ],
  });
