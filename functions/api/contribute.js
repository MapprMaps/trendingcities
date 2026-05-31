// Cloudflare Pages Function: POST /api/contribute
// Turns a community price suggestion into a pull request labeled
// `community-submission` (always human-reviewed; never auto-merged).
//
// Pages project env (Settings → Environment variables / Secrets):
//   TURNSTILE_SECRET  — Cloudflare Turnstile secret key (server-side)
//   GITHUB_TOKEN      — token with Contents + Pull requests + Issues write on the repo
const REPO = 'MapprMaps/trendingcities';
const PRICE_MIN = 5000, PRICE_MAX = 50_000_000;

const json = (obj, status = 200) =>
  new Response(JSON.stringify(obj), { status, headers: { 'Content-Type': 'application/json' } });

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

export async function onRequestPost({ request, env }) {
  let input;
  try { input = await request.json(); } catch { return json({ error: 'Invalid request.' }, 400); }
  const { citySlug, one, two, three, note, turnstileToken } = input || {};

  // 1. anti-spam — verify Turnstile
  if (!turnstileToken) return json({ error: 'Missing anti-spam token.' }, 400);
  const ip = request.headers.get('CF-Connecting-IP') || '';
  const form = new FormData();
  form.append('secret', env.TURNSTILE_SECRET);
  form.append('response', turnstileToken);
  if (ip) form.append('remoteip', ip);
  const ts = await (await fetch('https://challenges.cloudflare.com/turnstile/v0/siteverify', { method: 'POST', body: form })).json();
  if (!ts.success) return json({ error: 'Anti-spam check failed. Please try again.' }, 403);

  // 2. validate input
  if (!/^[a-z0-9-]+\/[a-z0-9-]+$/.test(citySlug || '')) return json({ error: 'Invalid city.' }, 400);
  const prices = { one, two, three };
  for (const [k, v] of Object.entries(prices)) {
    if (typeof v !== 'number' || !Number.isFinite(v) || v < PRICE_MIN || v > PRICE_MAX) {
      return json({ error: `The ${k}-bedroom price looks off (must be ${PRICE_MIN.toLocaleString()}–${PRICE_MAX.toLocaleString()} USD).` }, 400);
    }
  }
  const path = `data/cities/${citySlug}.json`;

  // 3. fetch the current record
  const cur = await gh(env, 'GET', `/repos/${REPO}/contents/${path}`);
  if (!cur.ok) return json({ error: 'That city is not in the dataset.' }, 404);
  let rec;
  try { rec = JSON.parse(atob(cur.data.content)); } catch { return json({ error: 'Could not read the record.' }, 500); }

  // 4. apply the proposed prices as a community-sourced, low-confidence update
  const asOf = new Date().toISOString().slice(0, 7);
  const cleanNote = (typeof note === 'string' ? note : '').slice(0, 280);
  const set = (key, value) => {
    rec.metrics[key] = { ...(rec.metrics[key] || {}), value, unit: 'USD', as_of: asOf,
      sources: ['community'], method: 'community-submission', confidence: 'low',
      ...(cleanNote ? { notes: cleanNote } : {}) };
  };
  set('home_price_1bed_usd', one); set('home_price_2bed_usd', two); set('home_price_3bed_usd', three);
  rec.provenance = { ...(rec.provenance || {}), status: 'draft', compiled_by: 'community', compiled_at: asOf + '-01' };
  const updated = btoa(unescape(encodeURIComponent(JSON.stringify(rec, null, 2) + '\n')));

  // 5. branch → commit → PR → label
  const main = await gh(env, 'GET', `/repos/${REPO}/git/ref/heads/main`);
  if (!main.ok) return json({ error: 'Repo error.' }, 502);
  const branch = `community/${citySlug.replace('/', '-')}-${Date.now()}`;
  const br = await gh(env, 'POST', `/repos/${REPO}/git/refs`, { ref: `refs/heads/${branch}`, sha: main.data.object.sha });
  if (!br.ok) return json({ error: 'Could not open a submission.' }, 502);
  const commit = await gh(env, 'PUT', `/repos/${REPO}/contents/${path}`, {
    message: `Community: price update for ${rec.city}, ${rec.country}`,
    content: updated, sha: cur.data.sha, branch,
  });
  if (!commit.ok) return json({ error: 'Could not save the submission.' }, 502);
  const pr = await gh(env, 'POST', `/repos/${REPO}/pulls`, {
    title: `Community: ${rec.city}, ${rec.country} price update`,
    head: branch, base: 'main',
    body: `Community-submitted price update for **${rec.city}, ${rec.country}**.\n\n`
      + `- 1-bed: $${one.toLocaleString()}\n- 2-bed: $${two.toLocaleString()}\n- 3-bed: $${three.toLocaleString()}\n`
      + (cleanNote ? `\n> ${cleanNote}\n` : '') + `\nAuto-checked by QC; held for human review.`,
  });
  if (!pr.ok) return json({ error: 'Could not open the submission.' }, 502);
  await gh(env, 'POST', `/repos/${REPO}/issues/${pr.data.number}/labels`, { labels: ['community-submission'] });

  return json({ ok: true, pr: pr.data.html_url, number: pr.data.number });
}
