import type { APIRoute } from 'astro';
import { cities, medians } from '../../lib/data';
import { SITE } from '../../lib/api';

// Affordability color by 3-bed price vs the global median (matches the site map).
function color(three: number): string {
  const r = three / medians.three;
  if (r < 0.55) return '#15A04A';
  if (r < 0.9) return '#2FB36C';
  if (r < 1.25) return '#F0A327';
  if (r < 2.0) return '#F4604D';
  return '#C23A2B';
}

export const GET: APIRoute = () => {
  const features = cities
    .filter((c) => typeof c.lat === 'number' && typeof c.lng === 'number')
    .map((c) => ({
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [c.lng, c.lat] },
      properties: {
        id: c.slug,
        name: c.city,
        country: c.country,
        is_district: c.isDistrict,
        page_url: `${SITE}${c.url}`,
        price_1bed_usd: c.one,
        price_2bed_usd: c.two,
        price_3bed_usd: c.three,
        color: color(c.three),
      },
    }));
  return new Response(JSON.stringify({ type: 'FeatureCollection', features }), {
    headers: {
      'Content-Type': 'application/geo+json; charset=utf-8',
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'public, max-age=3600',
    },
  });
};
