import type { APIRoute } from 'astro';
import { cities } from '../lib/data';

export const GET: APIRoute = async () => {
  const index = cities.map((c) => ({ city: c.city, country: c.country, url: c.url, lat: c.lat, lng: c.lng }));
  return new Response(JSON.stringify(index), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=3600' },
  });
};
