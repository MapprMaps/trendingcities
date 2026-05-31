#!/usr/bin/env python3
"""Open a data pull request — the reference path for research agents.

The caller (an agent) writes/updates record files under data/cities/ in a clone
of this repo, then runs this script to branch, commit, push, and open a PR with
the right label. The QC GitHub Action then validates it and (for clean,
high-confidence `agent-update` PRs) auto-merges.

Env:
  GITHUB_TOKEN  — token with PR + label write on the repo.
Usage:
  open-data-pr.py --branch agent/de-2026-06 --title "DE prices 2026-06" \\
                  --label agent-update --body "Monthly update for Germany."

Push uses the repo's configured remote/credentials (e.g. the deploy key).
"""
import argparse, json, os, subprocess, sys, urllib.request

REPO = "MapprMaps/trendingcities"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def git(*a, check=True):
    r = subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.exit(f"git {' '.join(a)} failed: {r.stderr.strip()}")
    return r.stdout.strip()

def get_token():
    """Prefer GITHUB_TOKEN; otherwise mint a GitHub App installation token so the
    PR is authored by trendingcities-agent[bot] (set GH_APP_ID + GH_APP_PRIVATE_KEY[_PATH])."""
    t = os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    here = os.path.dirname(os.path.abspath(__file__))
    out = subprocess.run([sys.executable, os.path.join(here, "gh-app-token.py")],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit("could not get a token (set GITHUB_TOKEN, or GH_APP_ID + key): " + out.stderr.strip())
    return out.stdout.strip()

TOKEN = None

def api(method, path, data=None):
    global TOKEN
    if TOKEN is None:
        TOKEN = get_token()
    req = urllib.request.Request("https://api.github.com" + path, method=method,
        headers={"Authorization": "token " + TOKEN,
                 "Accept": "application/vnd.github+json", "User-Agent": "tc-agent"})
    if data is not None:
        req.data = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as r:
            b = r.read(); return r.status, (json.loads(b) if b else {})
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", required=True)
    ap.add_argument("--title", required=True)
    ap.add_argument("--body", default="")
    ap.add_argument("--label", default="agent-update")
    a = ap.parse_args()

    changed = git("status", "--porcelain", "--", "data/cities")
    if not changed:
        sys.exit("nothing to submit — no changes under data/cities/")
    base = git("rev-parse", "--abbrev-ref", "HEAD") or "main"
    git("checkout", "-b", a.branch)
    git("add", "data/cities")
    git("-c", "commit.gpgsign=false", "commit", "-m", a.title)
    git("push", "-u", "origin", a.branch)
    git("checkout", base)  # leave the clone back on the base branch

    st, pr = api("POST", f"/repos/{REPO}/pulls",
                 {"title": a.title, "head": a.branch, "base": base, "body": a.body})
    if st >= 300:
        sys.exit(f"PR create failed {st}: {pr.get('message')}")
    num = pr["number"]
    api("POST", f"/repos/{REPO}/issues/{num}/labels", {"labels": [a.label]})
    print(f"opened PR #{num}: {pr['html_url']}")

if __name__ == "__main__":
    main()
