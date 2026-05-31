#!/usr/bin/env python3
"""Mint a short-lived GitHub App installation access token for this repo, and
print it to stdout. Agents (and CI) use it to act as `trendingcities-agent[bot]`
instead of any personal account.

Env:
  GH_APP_ID               — the GitHub App's numeric ID
  GH_APP_PRIVATE_KEY      — the PEM private key (full contents), OR
  GH_APP_PRIVATE_KEY_PATH — path to the .pem file
Repo is fixed to MapprMaps/trendingcities.
"""
import os, sys, json, time, urllib.request
import jwt  # PyJWT

REPO = "MapprMaps/trendingcities"

def private_key():
    k = os.environ.get("GH_APP_PRIVATE_KEY")
    if k:
        return k.replace("\\n", "\n")
    p = os.environ.get("GH_APP_PRIVATE_KEY_PATH")
    if p and os.path.exists(p):
        return open(p).read()
    sys.exit("set GH_APP_PRIVATE_KEY or GH_APP_PRIVATE_KEY_PATH")

def api(path, token, method="GET", data=None, bearer=False):
    auth = ("Bearer " if bearer else "token ") + token
    req = urllib.request.Request("https://api.github.com" + path, method=method,
        headers={"Authorization": auth, "Accept": "application/vnd.github+json", "User-Agent": "tc-app"})
    if data is not None:
        req.data = json.dumps(data).encode(); req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())

def main():
    app_id = os.environ["GH_APP_ID"]
    now = int(time.time())
    app_jwt = jwt.encode({"iat": now - 60, "exp": now + 540, "iss": app_id}, private_key(), algorithm="RS256")
    inst = api(f"/repos/{REPO}/installation", app_jwt, bearer=True)
    tok = api(f"/app/installations/{inst['id']}/access_tokens", app_jwt, method="POST", bearer=True)
    print(tok["token"])

if __name__ == "__main__":
    main()
