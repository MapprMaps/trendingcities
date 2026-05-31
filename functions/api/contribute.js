// Cloudflare Pages Function: POST /api/contribute
// Community price suggestion → a pull request labeled `community-submission`
// (always human-reviewed; never auto-merged). Two modes:
//   mode "update" — change an existing city's prices
//   mode "new"    — add a brand-new city/area
//
// Pages project env (Settings → Environment variables / Secrets):
//   TURNSTILE_SECRET  — Cloudflare Turnstile secret key
//   GITHUB_TOKEN      — token with Contents + Pull requests + Issues write on the repo
const REPO = 'MapprMaps/trendingcities';
const PRICE_MIN = 5000, PRICE_MAX = 50_000_000;

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });

function slugify(s) {
  return String(s).toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '')
    .replace(/[()'’.]/g, '').replace(/&/g, 'and')
    .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
}

async function gh(env, method, path, body) {
  const res = await fetch('https://api.github.com' + path, {
    method,
    headers: {
      Authorization: 'token ' + env.GITHUB_TOKEN,
      Accept: 'application/vnd.github+json',
      'User-Agent': 'trendingcities-contribute',
      'Content-Type': 'application/json',
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function metric(value, asOf, note) {
  return { value, unit: 'USD', as_of: asOf, sources: ['community'], method: 'community-submission',
    confidence: 'low', ...(note ? { notes: note } : {}) };
}

export async function onRequestPost({ request, env }) {
  let input;
  try { input = await request.json(); } catch { return json({ error: 'Invalid request.' }, 400); }
  const { mode = 'update', one, two, three, note, turnstileToken } = input || {};

  // 1. anti-spam
  if (!turnstileToken) return json({ error: 'Missing anti-spam token.' }, 400);
  const ip = request.headers.get('CF-Connecting-IP') || '';
  const form = new FormData();
  form.append('secret', env.TURNSTILE_SECRET);
  form.append('response', turnstileToken);
  if (ip) form.append('remoteip', ip);
  const ts = await (await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body: form })).json();
  if (!ts.success) return json({ error: 'Anti-spam check failed. Please try again.' }, 403);

  // 2. validate prices (shared)
  for (const [k, v] of Object.entries({ one, two, three })) {
    if (typeof v !== 'number' || !Number.isFinite(v) || v < PRICE_MIN || v > PRICE_MAX) {
      return json({ error: `The ${k}-bedroom price looks off (must be ${PRICE_MIN.toLocaleString()}–${PRICE_MAX.toLocaleString()} USD).` }, 400);
    }
  }
  const asOf = new Date().toISOString().slice(0, 7);
  const cleanNote = (typeof note === 'string' ? note : '').slice(0, 280);

  let path, rec, sha = undefined, label, title, displayName;

  if (mode === 'new') {
    const country = String(input.country || '').trim();
    const countryCode = String(input.countryCode || '').trim().toUpperCase();
    const city = String(input.city || '').trim();
    if (!country || !/^[A-Z]{2}$/.test(countryCode) || !city) return json({ error: 'Pick a country and enter a city name.' }, 400);
    const id = `${slugify(country)}/${slugify(city)}`;
    if (!/^[a-z0-9-]+\/[a-z0-9-]+$/.test(id)) return json({ error: 'That country/city name can\'t be turned into a valid entry.' }, 400);
    path = `data/cities/${id}.json`;
    // must not already exist
    const exists = await gh(env, 'GET', `/repos/${REPO}/contents/${path}`);
    if (exists.ok) return json({ error: `${city} is already in the dataset — use the city page to update it instead.` }, 409);
    rec = {
      schema_version: '1.0', id, city, country, country_code: countryCode,
      metrics: { home_price_1bed_usd: metric(one, asOf, cleanNote), home_price_2bed_usd: metric(two, asOf), home_price_3bed_usd: metric(three, asOf) },
      provenance: { compiled_by: 'community', compiled_at: asOf + '-01', status: 'draft' },
    };
    displayName = `${city}, ${country}`;
    title = `Community: add ${displayName}`;
  } else {
    const citySlug = String(input.citySlug || '');
    if (!/^[a-z0-9-]+\/[a-z0-9-]+$/.test(citySlug)) return json({ error: 'Invalid city.' }, 400);
    path = `data/cities/${citySlug}.json`;
    const cur = await gh(env, 'GET', `/repos/${REPO}/contents/${path}`);
    if (!cur.ok) return json({ error: 'That city is not in the dataset.' }, 404);
    try { rec = JSON.parse(atob(cur.data.content)); } catch { return json({ error: 'Could not read the record.' }, 500); }
    sha = cur.data.sha;
    rec.metrics.home_price_1bed_usd = { ...(rec.metrics.home_price_1bed_usd || {}), ...metric(one, asOf, cleanNote) };
    rec.metrics.home_price_2bed_usd = { ...(rec.metrics.home_price_2bed_usd || {}), ...metric(two, asOf) };
    rec.metrics.home_price_3bed_usd = { ...(rec.metrics.home_price_3bed_usd || {}), ...metric(three, asOf) };
    rec.provenance = { ...(rec.provenance || {}), status: 'draft', compiled_by: 'community', compiled_at: asOf + '-01' };
    displayName = `${rec.city}, ${rec.country}`;
    title = `Community: ${displayName} price update`;
  }

  // 3. branch → commit → PR → label
  const updated = btoa(unescape(encodeURIComponent(JSON.stringify(rec, null, 2) + '\n')));
  const main = await gh(env, 'GET', `/repos/${REPO}/git/ref/heads/main`);
  if (!main.ok) return json({ error: 'Repo error.' }, 502);
  const branch = `community/${rec.id.replace('/', '-')}-${Date.now()}`;
  const br = await gh(env, 'POST', `/repos/${REPO}/git/refs`, { ref: `refs/heads/${branch}`, sha: main.data.object.sha });
  if (!br.ok) return json({ error: 'Could not open a submission.' }, 502);
  const commitBody = { message: title, content: updated, branch };
  if (sha) commitBody.sha = sha;
  const commit = await gh(env, 'PUT', `/repos/${REPO}/contents/${path}`, commitBody);
  if (!commit.ok) return json({ error: 'Could not save the submission.' }, 502);
  const pr = await gh(env, 'POST', `/repos/${REPO}/pulls`, {
    title, head: branch, base: 'main',
    body: `${mode === 'new' ? 'New city' : 'Price update'} (community-submitted) for **${displayName}**.\n\n`
      + `- 1-bed: $${one.toLocaleString()}\n- 2-bed: $${two.toLocaleString()}\n- 3-bed: $${three.toLocaleString()}\n`
      + (cleanNote ? `\n> ${cleanNote}\n` : '') + `\nAuto-checked by QC; held for human review.`,
  });
  if (!pr.ok) return json({ error: 'Could not open the submission.' }, 502);
  await gh(env, 'POST', `/repos/${REPO}/issues/${pr.data.number}/labels`, { labels: ['community-submission'] });

  return json({ ok: true, pr: pr.data.html_url, number: pr.data.number });
}
