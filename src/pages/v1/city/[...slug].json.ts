import type { APIRoute, GetStaticPaths } from 'astro';
import { cities, relatedTo, districtsOf, type City } from '../../../lib/data';
import { apiCity, apiJson, API_META } from '../../../lib/api';

export const getStaticPaths: GetStaticPaths = () =>
  cities.map((c) => ({ params: { slug: c.slug }, props: { city: c } }));

export const GET: APIRoute = ({ props }) => {
  const city = props.city as City;
  return apiJson({
    meta: { ...API_META, endpoint: `/v1/city/${city.slug}.json` },
    ...apiCity(city),
    districts: city.isDistrict ? [] : districtsOf(city.slug).map(apiCity),
    related: relatedTo(city).map((r) => ({ id: r.slug, city: r.city, country: r.country, page_url: r.url })),
  });
};
