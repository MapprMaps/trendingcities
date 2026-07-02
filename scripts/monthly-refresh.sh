#!/bin/sh
# Monthly freshness engine for TrendingCities — the relevance cron.
# Re-pulls Numbeo's cost-of-living table, re-stamps the per-metric "last updated"
# dates to the current month, QC-gates the result against last month's values,
# and only then rebuilds + deploys + commits. On any QC anomaly it reverts the
# data changes and exits non-zero so cron-wrapper.sh alerts Andreas on Telegram.
#
# Intended cron (1st of the month, see ~/cron-jobs): wrapped by cron-wrapper.sh.
set -eu
REPO="/home/claude-svc/projects/trendingcities"
cd "$REPO"
. /home/claude-svc/.secrets 2>/dev/null || true
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; nvm use 22 >/dev/null 2>&1
git config core.sshCommand "ssh -i /home/claude-svc/.ssh/trendingcities_deploy -o IdentitiesOnly=yes"

echo "[refresh] $(date -u +%Y-%m-%dT%H:%M:%SZ) — fetching Numbeo rankings table"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
curl -fsS -A "$UA" "https://www.numbeo.com/cost-of-living/rankings.jsp" -o /tmp/numbeo_rankings.html
SIZE=$(wc -c < /tmp/numbeo_rankings.html)
if [ "$SIZE" -lt 100000 ]; then
  echo "[refresh] FAIL: rankings page only $SIZE bytes (expected >100k) — aborting, no changes"; exit 1
fi

echo "[refresh] enriching records (as_of = current month)"
python3 scripts/enrich-numbeo-table.py

if git diff --quiet -- data/cities; then
  echo "[refresh] no data changes this cycle — nothing to deploy"; exit 0
fi

echo "[refresh] QC gate"
if ! python3 scripts/qc-refresh.py; then
  echo "[refresh] QC failed — reverting data changes, leaving site untouched"
  git checkout -- data/cities
  exit 1
fi

echo "[refresh] build"
npm run build
echo "[refresh] deploy"
export CLOUDFLARE_API_TOKEN="$CLOUDFLARE_TOKEN"
export CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID"
npx wrangler@latest pages deploy dist --project-name=trendingcities-web --branch=main --commit-dirty=true

echo "[refresh] commit + push"
git add data/cities
git commit -q -m "Monthly data refresh $(date -u +%Y-%m): Numbeo cost-of-living + purchasing power"
git push origin main
echo "[refresh] done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
