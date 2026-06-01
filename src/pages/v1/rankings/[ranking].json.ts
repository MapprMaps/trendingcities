import type { APIRoute, GetStaticPaths } from 'astro';
import { mostExpensive3, mostAffordable1, best2Under250k } from '../../../lib/data';
import { apiCity, apiJson, API_META } from '../../../lib/api';

const RANKINGS: Record<string, { label: string; bed: string; list: any[] }> = {
  'most-expensive-3-bed': { label: 'Most expensive (3-bed)', bed: 'three_bed', list: mostExpensive3 },
  'most-affordable-1-bed': { label: 'Most affordable (1-bed)', bed: 'one_bed', list: mostAffordable1 },
  'best-2-bed-under-250k': { label: 'Best 2-bed under $250k', bed: 'two_bed', list: best2Under250k },
};

export const getStaticPaths: GetStaticPaths = () =>
  Object.keys(RANKINGS).map((ranking) => ({ params: { ranking } }));

export const GET: APIRoute = ({ params }) => {
  const r = RANKINGS[params.ranking as string];
  if (!r) return new Response('Not found', { status: 404 });
  return apiJson({
    meta: { ...API_META, endpoint: `/v1/rankings/${params.ranking}.json`, count: r.list.length },
    ranking: params.ranking,
    label: r.label,
    sorted_by: r.bed,
    cities: r.list.map(apiCity),
  });
};
