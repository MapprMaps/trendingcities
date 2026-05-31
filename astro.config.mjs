import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// Production site. Canonical host is www. The apex 301-redirects to www at the edge.
export default defineConfig({
  site: 'https://www.trendingcities.com',
  trailingSlash: 'always',
  output: 'static',
  integrations: [sitemap()],
  build: { format: 'directory' },
});
