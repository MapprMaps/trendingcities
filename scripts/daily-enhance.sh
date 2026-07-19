#!/bin/sh
# Daily incremental enhancement for TrendingCities — the "ongoing work" engine.
# Deepens real data on a traffic-prioritised batch of cities (currently: rents),
# QC-gates, then rebuilds + deploys + commits. No-ops cleanly when the backlog is
# empty or nothing was added. cron-wrapper.sh alerts on non-zero exit.
set -eu
REPO="/home/claude-svc/projects/trendingcities"
cd "$REPO"
# set -a so bare KEY=val lines in ~/.secrets are EXPORTED to python3 children
# (without it PERPLEXITY_API_KEY is empty in os.environ -> 401 on air/rents enrichment). Fixed 2026-07-18.
set -a; . /home/claude-svc/.secrets 2>/dev/null || true; set +a
export NVM_DIR="$HOME/.nvm"; . "$NVM_DIR/nvm.sh" >/dev/null 2>&1; nvm use 22 >/dev/null 2>&1
git config core.sshCommand "ssh -i /home/claude-svc/.ssh/trendingcities_deploy -o IdentitiesOnly=yes"

echo "[daily] $(date -u +%Y-%m-%dT%H:%M:%SZ) — enriching batch"
python3 scripts/daily-enhance.py --batch 40

if git diff --quiet -- data/cities; then
  echo "[daily] no new data this cycle — nothing to deploy"; exit 0
fi

echo "[daily] QC gate"
if ! python3 scripts/qc-refresh.py; then
  echo "[daily] QC failed — reverting, leaving site untouched"; git checkout -- data/cities; exit 1
fi

echo "[daily] build + deploy"
npm run build
export CLOUDFLARE_API_TOKEN="$CLOUDFLARE_TOKEN"
export CLOUDFLARE_ACCOUNT_ID="$CLOUDFLARE_ACCOUNT_ID"
npx wrangler@latest pages deploy dist --project-name=trendingcities-web --branch=main --commit-dirty=true

echo "[daily] commit + push"
git add -A
git commit -q -m "Daily enhance $(date -u +%Y-%m-%d): incremental data deepening (rents)"
git push origin main
echo "[daily] done $(date -u +%Y-%m-%dT%H:%M:%SZ)"
