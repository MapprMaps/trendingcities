import type { APIRoute } from 'astro';
import { cities } from '../../lib/data';
import { apiCity, apiJson, API_META } from '../../lib/api';

export const GET: APIRoute = () =>
  apiJson({
    meta: { ...API_META, endpoint: '/v1/cities.json', count: cities.length },
    cities: cities.map(apiCity),
  });
