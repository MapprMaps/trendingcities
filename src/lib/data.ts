import raw from '../data/prices.json';

export type Bed = 'one' | 'two' | 'three';

export interface RawRow {
  country: string;
  city: string;
  one_bed_usd: number;
  two_bed_usd: number;
  three_bed_usd: number;
}

export interface City {
  country: string;
  countrySlug: string;
  city: string;
  citySlug: string;
  slug: string; // country-slug/city-slug
  url: string;  // /city/{country}/{city}/
  one: number;
  two: number;
  three: number;
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
  const rows = raw as RawRow[];
  const seen = new Set<string>();
  const out: City[] = [];
  for (const r of rows) {
    const countrySlug = slugify(r.country);
    let citySlug = slugify(r.city);
    let slug = `${countrySlug}/${citySlug}`;
    let n = 2;
    while (seen.has(slug)) {
      citySlug = `${slugify(r.city)}-${n++}`;
      slug = `${countrySlug}/${citySlug}`;
    }
    seen.add(slug);
    out.push({
      country: r.country,
      countrySlug,
      city: r.city,
      citySlug,
      slug,
      url: `/city/${slug}/`,
      one: r.one_bed_usd,
      two: r.two_bed_usd,
      three: r.three_bed_usd,
    });
  }
  return out;
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
