#!/usr/bin/env python3
"""Track public-repo signals over time.

Polls GitHub API for stars, forks, watchers, issues, recent stargazers,
traffic (clones + visitors if available). Appends a row to a CSV.

Run periodically (cron, scheduled task) or interactively to get a one-shot
snapshot.

Usage:
    python scripts/track_signals.py [--repo MGBuilds9/exo] [--out signals.csv]
    python scripts/track_signals.py --snapshot   # print one-shot, don't append

Privacy: Uses `gh` CLI auth. The traffic endpoints (clones, visitors)
require push access to the repo — which you have, since you own it.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

DEFAULT_REPO = "MGBuilds9/exo"
DEFAULT_OUT = Path.home() / "exo-tracking" / "signals.csv"


def gh_api(endpoint: str) -> dict | list | None:
    """Call gh api. Returns parsed JSON or None on failure."""
    os.environ["MSYS_NO_PATHCONV"] = "1"
    try:
        proc = subprocess.run(
            ["gh", "api", endpoint],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if proc.returncode != 0:
            return None
        return json.loads(proc.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def snapshot(repo: str) -> dict:
    """One snapshot of signals."""
    now = datetime.now(timezone.utc)
    out = {
        "ts": now.isoformat(),
        "repo": repo,
        "stars": None,
        "forks": None,
        "watchers": None,
        "open_issues": None,
        "open_pull_requests": None,
        "subscribers": None,
        "size_kb": None,
        "stargazers_last_7d": 0,
        "stargazers_all_time": [],
        "traffic_views_14d": None,
        "traffic_uniques_14d": None,
        "traffic_clones_14d": None,
        "traffic_clones_uniques_14d": None,
        "top_referrers": [],
        "top_paths": [],
    }

    # Basic repo metadata
    meta = gh_api(f"/repos/{repo}")
    if meta:
        out["stars"] = meta.get("stargazers_count")
        out["forks"] = meta.get("forks_count")
        out["watchers"] = meta.get("watchers_count")
        out["open_issues"] = meta.get("open_issues_count")
        out["subscribers"] = meta.get("subscribers_count")
        out["size_kb"] = meta.get("size")

    # Pull requests (separate from issues count in newer API)
    prs = gh_api(f"/repos/{repo}/pulls?state=open&per_page=100")
    if isinstance(prs, list):
        out["open_pull_requests"] = len(prs)

    # Recent stargazers (last 100)
    # The Accept header is needed but gh api adds defaults; we use the standard endpoint
    stargazers = gh_api(f"/repos/{repo}/stargazers?per_page=100&sort=newest")
    if isinstance(stargazers, list):
        # Newer GH API returns objects with `user` keyed; older returns user dicts directly
        usernames = []
        for s in stargazers[:20]:
            if isinstance(s, dict):
                user = s.get("user") or s
                usernames.append(user.get("login", "?"))
        out["stargazers_all_time"] = usernames
        out["stargazers_last_7d"] = len(usernames)  # rough; this is "last 100" capped

    # Traffic — requires push access (which we have on our own repo)
    views = gh_api(f"/repos/{repo}/traffic/views")
    if views:
        out["traffic_views_14d"] = views.get("count")
        out["traffic_uniques_14d"] = views.get("uniques")

    clones = gh_api(f"/repos/{repo}/traffic/clones")
    if clones:
        out["traffic_clones_14d"] = clones.get("count")
        out["traffic_clones_uniques_14d"] = clones.get("uniques")

    referrers = gh_api(f"/repos/{repo}/traffic/popular/referrers")
    if isinstance(referrers, list):
        out["top_referrers"] = [
            f"{r.get('referrer','?')}:{r.get('count',0)}/{r.get('uniques',0)}"
            for r in referrers[:5]
        ]

    paths = gh_api(f"/repos/{repo}/traffic/popular/paths")
    if isinstance(paths, list):
        out["top_paths"] = [
            f"{p.get('path','?')[:60]}:{p.get('count',0)}"
            for p in paths[:5]
        ]

    return out


def append_csv(snap: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "ts", "repo", "stars", "forks", "watchers", "open_issues",
        "open_pull_requests", "subscribers", "size_kb",
        "stargazers_last_7d", "stargazers_all_time",
        "traffic_views_14d", "traffic_uniques_14d",
        "traffic_clones_14d", "traffic_clones_uniques_14d",
        "top_referrers", "top_paths",
    ]
    row = {k: snap.get(k) for k in fieldnames}
    # Lists → semicolon-joined strings for CSV
    for k in ("stargazers_all_time", "top_referrers", "top_paths"):
        v = row.get(k)
        row[k] = "; ".join(str(x) for x in v) if isinstance(v, list) else (v or "")

    write_header = not out_path.exists()
    with out_path.open("a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        if write_header:
            w.writeheader()
        w.writerow(row)


def pretty_print(snap: dict, prev: dict | None = None) -> None:
    print(f"=== {snap['repo']} @ {snap['ts']} ===")
    def delta(k):
        if prev is None or prev.get(k) is None or snap.get(k) is None:
            return ""
        try:
            d = int(snap[k]) - int(prev[k])
            if d > 0: return f"  (+{d})"
            if d < 0: return f"  ({d})"
            return ""
        except (TypeError, ValueError):
            return ""
    print(f"  stars:                {snap['stars']}{delta('stars')}")
    print(f"  forks:                {snap['forks']}{delta('forks')}")
    print(f"  watchers (subscribers): {snap['subscribers']}{delta('subscribers')}")
    print(f"  open_issues:          {snap['open_issues']}{delta('open_issues')}")
    print(f"  open_PRs:             {snap['open_pull_requests']}{delta('open_pull_requests')}")
    if snap.get("traffic_views_14d") is not None:
        print(f"  traffic views (14d):  {snap['traffic_views_14d']} ({snap['traffic_uniques_14d']} unique)")
        print(f"  traffic clones (14d): {snap['traffic_clones_14d']} ({snap['traffic_clones_uniques_14d']} unique)")
    if snap["top_referrers"]:
        print(f"  top referrers:        {snap['top_referrers']}")
    if snap["top_paths"]:
        print(f"  top paths:            {snap['top_paths']}")
    if snap.get("stargazers_all_time"):
        print(f"  recent stargazers:    {snap['stargazers_all_time'][:10]}")


def read_last_row(out_path: Path) -> dict | None:
    if not out_path.exists():
        return None
    rows = list(csv.DictReader(out_path.open(encoding="utf-8")))
    return rows[-1] if rows else None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT,
                   help="CSV log path (default: ~/exo-tracking/signals.csv)")
    p.add_argument("--snapshot", action="store_true",
                   help="Print one-shot snapshot; don't append to CSV")
    p.add_argument("--quiet", action="store_true",
                   help="Just write the row; suppress stdout")
    args = p.parse_args()

    snap = snapshot(args.repo)
    if not args.snapshot:
        prev = read_last_row(args.out)
        append_csv(snap, args.out)
        if not args.quiet:
            pretty_print(snap, prev)
            print(f"\n  appended to: {args.out}")
    else:
        pretty_print(snap)


if __name__ == "__main__":
    main()
