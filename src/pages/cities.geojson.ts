import type { APIRoute } from 'astro';
import { cities, medians } from '../lib/data';
import { usdShort } from '../lib/format';

// Affordability color by 3-bed price vs the global median.
function color(three: number): string {
  const r = three / medians.three;
  if (r < 0.55) return '#15A04A'; // very affordable — green
  if (r < 0.9) return '#2FB36C';  // below median — light green
  if (r < 1.25) return '#F0A327'; // around median — amber
  if (r < 2.0) return '#F4604D';  // above median — coral
  return '#C23A2B';               // very expensive — deep red
}

export const GET: APIRoute = () => {
  const features = cities
    .filter((c) => typeof c.lat === 'number' && typeof c.lng === 'number')
    .map((c) => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.lng, c.lat] },
      properties: {
        name: c.city,
        country: c.country,
        url: c.url,
        price: usdShort(c.three),
        color: color(c.three),
      },
    }));
  return new Response(JSON.stringify({ type: 'FeatureCollection', features }), {
    headers: { 'Content-Type': 'application/json', 'Cache-Control': 'public, max-age=3600' },
  });
};
