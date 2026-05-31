#!/usr/bin/env python3
"""QC for TrendingCities data PRs. Validates every changed data/cities/**.json
record against the schema + plausibility rules, and compares to the base
version to flag big swings. Writes verdict.json and prints a markdown report.

Usage: qc-data-pr.py <base_sha>
"""
import json, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = os.path.join(ROOT, "schema", "city-record.schema.json")

PRICE_MIN, PRICE_MAX = 5_000, 50_000_000
SWING_WARN = 0.40  # >40% change vs base on a price → needs human review

def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True).stdout

def changed_record_files(base):
    out = git("diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD", "--", "data/cities")
    return [f for f in out.splitlines() if f.endswith(".json")]

def base_version(base, path):
    r = subprocess.run(["git", "show", f"{base}:{path}"], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def check_record(path, rec, base_rec, validate):
    errors, warnings = [], []
    try:
        validate(rec)
    except Exception as e:
        errors.append(f"schema: {str(e).splitlines()[0]}")
        return errors, warnings, "low"
    m = re.search(r"data/cities/([^/]+)/([^/]+)\.json$", path)
    if m and rec.get("id") != f"{m.group(1)}/{m.group(2)}":
        errors.append(f"id `{rec.get('id')}` does not match file path `{m.group(1)}/{m.group(2)}`")
    mt = rec.get("metrics", {})
    def price(k):
        return (mt.get(k) or {}).get("value")
    one, two, three = price("home_price_1bed_usd"), price("home_price_2bed_usd"), price("home_price_3bed_usd")
    for k, v in [("1bed", one), ("2bed", two), ("3bed", three)]:
        if v is None:
            errors.append(f"missing home_price_{k}_usd")
        elif not (PRICE_MIN <= v <= PRICE_MAX):
            errors.append(f"{k} price {v} outside sane bounds [{PRICE_MIN:,}–{PRICE_MAX:,}]")
    if None not in (one, two, three) and not (one <= two <= three):
        # Warning, not a hard error: a premium small unit can legitimately outprice
        # a larger one. Flags for human review (blocks auto-merge) without failing the PR.
        warnings.append(f"price ordering unusual: 1bed {one:,} / 2bed {two:,} / 3bed {three:,} (expected 1≤2≤3) — confirm it's real")
    confidences = []
    for k, mv in mt.items():
        if not mv.get("sources"):
            errors.append(f"{k}: missing sources")
        if not mv.get("as_of"):
            errors.append(f"{k}: missing as_of")
        if mv.get("confidence"):
            confidences.append(mv["confidence"])
    if base_rec:
        bmt = base_rec.get("metrics", {})
        for k in ("home_price_1bed_usd", "home_price_2bed_usd", "home_price_3bed_usd"):
            nv = (mt.get(k) or {}).get("value")
            ov = (bmt.get(k) or {}).get("value")
            if nv and ov and ov > 0 and abs(nv - ov) / ov > SWING_WARN:
                warnings.append(f"{k}: {abs(nv-ov)/ov*100:.0f}% change vs current ({ov:,} → {nv:,}) — needs a look")
    min_conf = "high" if confidences and all(c == "high" for c in confidences) else (
        "low" if "low" in confidences else "medium")
    return errors, warnings, min_conf

def main():
    base = sys.argv[1] if len(sys.argv) > 1 else "HEAD~1"
    schema = json.load(open(SCHEMA))
    import jsonschema
    validator = jsonschema.Draft202012Validator(schema)
    def validate(rec):
        errs = sorted(validator.iter_errors(rec), key=lambda e: list(e.path))
        if errs:
            raise ValueError(errs[0].message)

    files = changed_record_files(base)
    lines = ["## 🔍 Data QC report", ""]
    all_pass, all_auto = True, True
    if not files:
        lines.append("No `data/cities/**.json` records changed in this PR — nothing to QC.")
        json.dump({"overall_pass": True, "auto_mergeable": False, "report_md": "\n".join(lines), "n_files": 0}, open("verdict.json", "w"))
        print("\n".join(lines)); return

    lines.append(f"Checked **{len(files)}** changed record file(s):\n")
    for path in files:
        try:
            rec = json.load(open(os.path.join(ROOT, path)))
        except Exception as e:
            lines.append(f"- ❌ `{path}` — invalid JSON: {e}"); all_pass = all_auto = False; continue
        errors, warnings, conf = check_record(path, rec, base_version(base, path), validate)
        name = f"{rec.get('city','?')}, {rec.get('country','?')}"
        if errors:
            all_pass = all_auto = False
            lines.append(f"- ❌ **{name}** (`{path}`)")
            lines += [f"    - {e}" for e in errors]
        elif warnings:
            all_auto = False
            lines.append(f"- ⚠️ **{name}** — valid, but flagged for review:")
            lines += [f"    - {w}" for w in warnings]
        else:
            lines.append(f"- ✅ **{name}** — valid, plausible" + ("" if conf == "high" else f" (confidence: {conf})"))
            if conf != "high":
                all_auto = False

    lines.append("")
    if all_pass and all_auto:
        lines.append("**Verdict: PASS** — clean, high-confidence. Eligible for auto-merge from a trusted agent author.")
    elif all_pass:
        lines.append("**Verdict: PASS with notes** — valid but needs a human approval (swings / non-high confidence).")
    else:
        lines.append("**Verdict: FAIL** — fix the errors above. Not mergeable.")

    json.dump({"overall_pass": all_pass, "auto_mergeable": all_pass and all_auto,
               "report_md": "\n".join(lines), "n_files": len(files)}, open("verdict.json", "w"))
    print("\n".join(lines))

if __name__ == "__main__":
    main()
