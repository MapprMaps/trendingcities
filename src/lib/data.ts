// Per-city record files are the dataset source of truth (data/cities/**.json),
// each conforming to city-record.schema.json. The FILE PATH is the slug.
const recordModules = import.meta.glob('/data/cities/**/*.json', { eager: true }) as Record<
  string,
  { default: CityRecord }
>;

export type Bed = 'one' | 'two' | 'three';

interface MetricValue {
  value: number;
  unit: string;
  as_of: string;
  sources: string[];
  confidence?: string;
  method?: string;
}
export interface CityRecord {
  schema_version: string;
  id: string;
  city: string;
  country: string;
  country_code: string;
  coordinates?: { lat: number; lng: number };
  media?: { photo_ids?: string[]; hero?: Hero };
  airports?: Airport[];
  metrics: Record<string, MetricValue>;
  provenance: { compiled_by: string; compiled_at: string; status: string };
}

export interface Hero { url: string; title: string; photographer: string; username?: string; ss_url?: string; source: string; license: string; }
export interface Airport { iata?: string; icao: string; name: string; type?: string; distance_km: number; destinations?: number; airlines?: number; url: string; }

export interface City {
  country: string;
  countryCode: string;
  countrySlug: string;
  city: string;
  citySlug: string;
  slug: string; // country-slug/city-slug
  url: string;  // /city/{country}/{city}/
  one: number;
  two: number;
  three: number;
  asOf: string;       // metric as_of (e.g. "2026-05")
  sources: string[];  // upstream sources for the price metrics
  lat?: number;
  lng?: number;
  hero?: Hero;
  airports?: Airport[];
}

export const DATA_VERSION = '2026.1';
export const DATA_UPDATED = '2026-05'; // starter dataset month
export const DATA_LABEL = 'Median home prices · starter dataset v' + DATA_VERSION;
export const DATA_SOURCES = 'Compiled from GlobalPropertyGuide, Numbeo and public web research';

export function slugify(s: string): string {
  return s
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[()]/g, '')
    .replace(/['’.]/g, '')
    .replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function build(): City[] {
  const out: City[] = [];
  for (const [path, mod] of Object.entries(recordModules)) {
    const rec = mod.default;
    if (rec?.provenance?.status !== 'published') continue; // only published records go live
    // Slug is the file path: /data/cities/{countrySlug}/{citySlug}.json
    const m = path.match(/\/data\/cities\/([^/]+)\/([^/]+)\.json$/);
    if (!m) continue;
    const countrySlug = m[1];
    const citySlug = m[2];
    const one = rec.metrics.home_price_1bed_usd;
    const two = rec.metrics.home_price_2bed_usd;
    const three = rec.metrics.home_price_3bed_usd;
    if (!one || !two || !three) continue;
    out.push({
      country: rec.country,
      countryCode: rec.country_code,
      countrySlug,
      city: rec.city,
      citySlug,
      slug: `${countrySlug}/${citySlug}`,
      url: `/city/${countrySlug}/${citySlug}/`,
      one: one.value,
      two: two.value,
      three: three.value,
      asOf: three.as_of || two.as_of || one.as_of,
      sources: three.sources || [],
      lat: rec.coordinates?.lat,
      lng: rec.coordinates?.lng,
      hero: rec.media?.hero,
      airports: rec.airports,
    });
  }
  return out.sort((a, b) => a.country.localeCompare(b.country) || a.city.localeCompare(b.city));
}

export const cities: City[] = build();

function median(nums: number[]): number {
  const s = [...nums].sort((a, b) => a - b);
  const m = Math.floor(s.length / 2);
  return s.length % 2 ? s[m] : Math.round((s[m - 1] + s[m]) / 2);
}

export const medians = {
  one: median(cities.map((c) => c.one)),
  two: median(cities.map((c) => c.two)),
  three: median(cities.map((c) => c.three)),
};

export const bedField: Record<Bed, keyof Pick<City, 'one' | 'two' | 'three'>> = {
  one: 'one',
  two: 'two',
  three: 'three',
};

export const bedLabel: Record<Bed, string> = {
  one: '1-bed',
  two: '2-bed',
  three: '3-bed',
};

/** % difference vs the dataset median for a bedroom type. Negative = cheaper (more affordable). */
export function vsMedian(price: number, bed: Bed): number {
  const m = medians[bed];
  return Math.round(((price - m) / m) * 1000) / 10;
}

export interface CountryAgg {
  country: string;
  countrySlug: string;
  count: number;
  one: number;
  two: number;
  three: number;
  cities: City[];
}

export function byCountry(): CountryAgg[] {
  const map = new Map<string, City[]>();
  for (const c of cities) {
    if (!map.has(c.country)) map.set(c.country, []);
    map.get(c.country)!.push(c);
  }
  const out: CountryAgg[] = [];
  for (const [country, list] of map) {
    out.push({
      country,
      countrySlug: list[0].countrySlug,
      count: list.length,
      one: median(list.map((c) => c.one)),
      two: median(list.map((c) => c.two)),
      three: median(list.map((c) => c.three)),
      cities: [...list].sort((a, b) => a.city.localeCompare(b.city)),
    });
  }
  return out.sort((a, b) => a.country.localeCompare(b.country));
}

export const countries = byCountry();
export const COUNTRY_COUNT = countries.length;
export const CITY_COUNT = cities.length;

/** Related = other cities in the same country (excluding self). */
export function relatedTo(c: City, limit = 6): City[] {
  return cities
    .filter((x) => x.country === c.country && x.slug !== c.slug)
    .sort((a, b) => a.three - b.three)
    .slice(0, limit);
}

// ── Rankings ─────────────────────────────────────────────────────────────
export const mostExpensive3 = [...cities].sort((a, b) => b.three - a.three);
export const mostAffordable1 = [...cities].sort((a, b) => a.one - b.one);
export const best2Under250k = [...cities]
  .filter((c) => c.two < 250000)
  .sort((a, b) => a.two - b.two);
export const countryRanking = [...countries].sort((a, b) => b.three - a.three);
