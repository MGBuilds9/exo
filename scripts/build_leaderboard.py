"""Build the public exo recommend leaderboard.

Iterates every capability in the taxonomy, fetches live GitHub signals,
scores all candidates, and renders a static site to `docs/`:
- docs/index.html            — overview, all capabilities at a glance
- docs/c/<slug>.html         — full ranking + signals per capability
- docs/data.json             — raw machine-readable data
- docs/data.csv              — flat CSV for spreadsheet imports

Designed to be re-run weekly by a GitHub Actions cron — the diff is the
moving leaderboard.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timezone
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exo_runtime.recommend import (
    list_capabilities, score_candidates, score_as_dict,
)


# === Data build ==============================================================

def build_snapshot(weight_profile: str = "default",
                   license_constraint: str = "any",
                   verbose: bool = False) -> dict:
    """Score every capability's candidates. Returns full snapshot dict."""
    caps = list_capabilities()
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weight_profile": weight_profile,
        "license_constraint": license_constraint,
        "exo_version": "0.3.0",
        "source": "https://github.com/MGBuilds9/exo",
        "capabilities": [],
    }
    for cap in caps:
        slug = cap["slug"]
        if verbose:
            print(f"=== {slug} ({len(cap['candidate_pool'])} candidates) ===")
        scored = score_candidates(
            cap["candidate_pool"],
            license_constraint=license_constraint,
            weight_profile=weight_profile,
            verbose=verbose,
        )
        snapshot["capabilities"].append({
            "slug": slug,
            "description": cap["description"],
            "category": cap.get("category", ""),
            "refresh_cadence": cap.get("refresh_cadence", ""),
            "notes": cap.get("notes", ""),
            "candidate_count": len(scored),
            "rankings": [score_as_dict(s) for s in scored],
        })
    return snapshot


# === HTML rendering ===========================================================

STYLE_BLOCK = """
<style>
  :root {
    --bg: #0a0e14; --panel: #11161e; --line: #1f2630;
    --text: #d4dae3; --muted: #8b949e; --accent: #58a6ff;
    --good: #3fb950; --warn: #d29922; --bad: #f85149;
    --chip: #21262d;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; padding: 0;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    line-height: 1.55;
  }
  .wrap { max-width: 1100px; margin: 0 auto; padding: 32px 24px 80px; }
  header { padding-bottom: 28px; border-bottom: 1px solid var(--line); margin-bottom: 32px; }
  h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -0.02em; }
  h2 { margin: 32px 0 12px; font-size: 20px; }
  h3 { margin: 24px 0 8px; font-size: 16px; }
  .sub { color: var(--muted); font-size: 14px; }
  .meta { color: var(--muted); font-size: 13px; margin-top: 8px; }
  a { color: var(--accent); text-decoration: none; }
  a:hover { text-decoration: underline; }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
    padding: 18px 20px; margin: 14px 0;
  }
  .card h3 { margin-top: 0; }
  .row { display: flex; justify-content: space-between; gap: 24px; align-items: baseline; }
  .chip {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    background: var(--chip); color: var(--muted); font-size: 11px;
    font-family: "SF Mono", Menlo, monospace; margin-right: 4px;
  }
  .grade {
    font-weight: 600; font-size: 22px; min-width: 60px; text-align: right;
    font-family: "SF Mono", Menlo, monospace;
  }
  .grade-good { color: var(--good); }
  .grade-mid  { color: var(--warn); }
  .grade-low  { color: var(--bad); }
  table {
    width: 100%; border-collapse: collapse; margin: 12px 0;
    font-size: 13px;
  }
  th, td {
    padding: 8px 10px; text-align: left;
    border-bottom: 1px solid var(--line);
  }
  th { font-weight: 600; color: var(--muted); }
  td.num { font-family: "SF Mono", Menlo, monospace; text-align: right; }
  .rationale {
    font-size: 12px; color: var(--muted); font-family: "SF Mono", Menlo, monospace;
    background: var(--bg); padding: 10px 12px; border-radius: 4px;
    margin-top: 8px; white-space: pre-wrap; max-height: 200px; overflow-y: auto;
  }
  .legend { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .toc { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 12px; }
  .toc a {
    display: block; padding: 14px 16px; border: 1px solid var(--line);
    border-radius: 6px; background: var(--panel);
    color: var(--text);
  }
  .toc a:hover { border-color: var(--accent); text-decoration: none; }
  .toc-cap-name { font-weight: 600; font-size: 14px; }
  .toc-cap-leader { color: var(--accent); font-family: "SF Mono", Menlo, monospace; font-size: 13px; margin-top: 6px; }
  .toc-cap-desc { color: var(--muted); font-size: 12px; margin-top: 4px; }
  footer { margin-top: 60px; padding-top: 24px; border-top: 1px solid var(--line); color: var(--muted); font-size: 13px; }
  .pill {
    display: inline-block; padding: 2px 8px; border-radius: 12px;
    background: var(--chip); color: var(--muted); font-size: 11px;
  }
  .install {
    background: var(--panel); border: 1px solid var(--line); border-radius: 6px;
    padding: 14px 18px; font-family: "SF Mono", Menlo, monospace; font-size: 13px;
    margin: 16px 0;
  }
</style>
"""


def _grade_class(score: float) -> str:
    if score >= 7.0: return "grade-good"
    if score >= 4.5: return "grade-mid"
    return "grade-low"


def _human_age(iso: str | None) -> str:
    if not iso: return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400
        if days < 7: return f"{int(days)}d"
        if days < 60: return f"{int(days)}d"
        if days < 365: return f"{int(days/30)}mo"
        return f"{days/365:.1f}y"
    except Exception:
        return "?"


def _index_html(snapshot: dict) -> str:
    gen = snapshot["generated_at"][:10]
    rows = []
    for cap in snapshot["capabilities"]:
        slug = cap["slug"]
        rankings = cap["rankings"]
        leader = rankings[0] if rankings else None
        leader_html = ""
        if leader and leader.get("composite", 0) > 0:
            leader_html = f"""
            <div class="toc-cap-leader">{escape(leader['full_name'])} · {leader['composite']}/10</div>"""
        else:
            leader_html = '<div class="toc-cap-leader">no scoreable candidates</div>'
        rows.append(f"""
        <a href="c/{escape(slug)}.html">
          <div class="toc-cap-name">{escape(slug)}</div>
          {leader_html}
          <div class="toc-cap-desc">{escape(cap['description'])}</div>
        </a>""")

    top_n = sum(1 for c in snapshot["capabilities"]
                if c["rankings"] and c["rankings"][0].get("composite", 0) > 0)
    total_candidates = sum(c["candidate_count"] for c in snapshot["capabilities"])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>exo · best open-source repos by capability</title>
<meta name="description" content="Data-driven leaderboard of the best open-source repos by AI infrastructure capability. Refreshed weekly. No LLM bias.">
{STYLE_BLOCK}
</head>
<body>
<div class="wrap">
  <header>
    <h1>exo · best open-source repos by capability</h1>
    <div class="sub">Data-driven scoring against live GitHub signals. No LLM bias in the ranking.</div>
    <div class="meta">
      <span class="pill">refreshed {escape(gen)}</span>
      <span class="pill">{top_n} capabilities</span>
      <span class="pill">{total_candidates} candidates evaluated</span>
      <span class="pill">profile: default</span>
    </div>
  </header>

  <p>This is what <code>exo recommend</code> produces, run weekly across every capability. Each leaderboard scores candidate repos against four sub-scores — maintenance, popularity, governance, and license fit — using a fixed deterministic formula against live GitHub data. The LLM never picks the repo. We do, with data you can audit.</p>

  <div class="install">
    pip install exo-cli &nbsp;&nbsp;<span style="color:var(--muted)">·</span>&nbsp;&nbsp; <a href="https://github.com/MGBuilds9/exo">github.com/MGBuilds9/exo</a>
  </div>

  <h2>Capabilities</h2>
  <div class="toc">
    {''.join(rows)}
  </div>

  <h2>How this is scored</h2>
  <p>For each candidate repo we fetch live GitHub signals via the <code>gh</code> CLI: stars, forks, push recency, recent commit count, recent release count, contributor count, open issue count, age, license, archive status. Four sub-scores each contribute to a 0–10 composite:</p>
  <ul>
    <li><strong>Maintenance</strong> — push recency + 90-day commit volume + recent releases. Heavy penalty for archived/disabled.</li>
    <li><strong>Popularity</strong> — stars with a stars-per-day momentum bonus.</li>
    <li><strong>Governance</strong> — contributor count, healthy issue backlog, age.</li>
    <li><strong>License fit</strong> — matches your constraint (any / permissive / no-AGPL / no-copyleft).</li>
  </ul>
  <p>Weights for the default profile: maintenance 30%, popularity 30%, governance 25%, license fit 15%. Other profiles available in the CLI: <code>reliable</code>, <code>cutting-edge</code>, <code>commercial</code>.</p>

  <h2>Use it locally</h2>
  <p>The leaderboard lives here because it's a side-effect — the real product is the CLI. Get a personalized ranking with your own license constraint and weight profile:</p>
  <div class="install">
    exo recommend &lt;capability&gt; --weight-profile reliable --license no-agpl
  </div>
  <p>Or, even better: describe what you're trying to build and let <code>exo solve</code> propose what capability you need, then chain to <code>exo recommend</code> automatically.</p>

  <footer>
    <p>Generated by <a href="https://github.com/MGBuilds9/exo/blob/main/scripts/build_leaderboard.py">scripts/build_leaderboard.py</a> on {escape(snapshot['generated_at'])}.</p>
    <p>Raw data: <a href="data.json">data.json</a> · <a href="data.csv">data.csv</a>. PRs to expand the candidate pools welcome.</p>
  </footer>
</div>
</body>
</html>
"""


def _capability_html(snapshot: dict, cap: dict) -> str:
    rankings = cap["rankings"]
    rows = []
    for i, r in enumerate(rankings, 1):
        sig = r.get("signals", {})
        score = r.get("composite", 0)
        cls = _grade_class(score)
        rationale = "\n".join(r.get("rationale", []))
        license_label = sig.get("license_key") or "—"
        archived = " <span class='chip' style='color:var(--bad)'>archived</span>" if sig.get("archived") else ""
        rows.append(f"""
        <tr>
          <td class="num">{i}</td>
          <td><a href="https://github.com/{escape(r['full_name'])}" target="_blank" rel="noopener">{escape(r['full_name'])}</a>{archived}</td>
          <td class="num"><span class="{cls}">{score}</span></td>
          <td class="num">{r.get('maintenance',0)}</td>
          <td class="num">{r.get('popularity',0)}</td>
          <td class="num">{r.get('governance',0)}</td>
          <td class="num">{r.get('license_fit',0)}</td>
          <td class="num">{sig.get('stars',0):,}</td>
          <td class="num">{_human_age(sig.get('pushed_at'))} ago</td>
          <td>{escape(license_label)}</td>
        </tr>
        <tr>
          <td colspan="10"><details><summary class="legend">show rationale</summary>
            <div class="rationale">{escape(rationale) or '(no rationale)'}</div>
          </details></td>
        </tr>""")

    notes_html = ""
    if cap.get("notes"):
        notes_html = f"<div class='card'><h3>Curator notes</h3><div class='legend' style='white-space:pre-wrap'>{escape(cap['notes'])}</div></div>"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>exo · {escape(cap['slug'])} leaderboard</title>
<meta name="description" content="Best open-source {escape(cap['description'])}. Data-driven scoring.">
{STYLE_BLOCK}
</head>
<body>
<div class="wrap">
  <header>
    <div class="sub"><a href="../index.html">← all capabilities</a></div>
    <h1>{escape(cap['slug'])}</h1>
    <div class="sub">{escape(cap['description'])}</div>
    <div class="meta">
      <span class="pill">category: {escape(cap.get('category','—'))}</span>
      <span class="pill">{cap['candidate_count']} candidates</span>
      <span class="pill">refresh: {escape(cap.get('refresh_cadence','—'))}</span>
      <span class="pill">scored {escape(snapshot['generated_at'][:10])}</span>
    </div>
  </header>

  {notes_html}

  <table>
    <thead>
      <tr>
        <th>#</th><th>Repository</th><th class="num">Composite</th>
        <th class="num">Maint.</th><th class="num">Pop.</th>
        <th class="num">Gov.</th><th class="num">License</th>
        <th class="num">Stars</th><th class="num">Pushed</th>
        <th>License</th>
      </tr>
    </thead>
    <tbody>
      {''.join(rows)}
    </tbody>
  </table>

  <div class="card">
    <h3>Use this in your project</h3>
    <p>To run this evaluation locally with your own constraints:</p>
    <div class="install">exo recommend {escape(cap['slug'])} --weight-profile reliable --license no-agpl</div>
    <p>The CLI supports four weight profiles: <code>default</code> (balanced), <code>reliable</code> (favor maintenance + governance), <code>cutting-edge</code> (favor popularity), <code>commercial</code> (favor license fit).</p>
  </div>

  <footer>
    <p><a href="../data.json">data.json</a> · <a href="../index.html">all capabilities</a> · <a href="https://github.com/MGBuilds9/exo">exo on GitHub</a></p>
  </footer>
</div>
</body>
</html>
"""


# === CSV export ==============================================================

def _write_csv(snapshot: dict, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "capability", "rank", "repo", "composite",
            "maintenance", "popularity", "governance", "license_fit",
            "stars", "forks", "open_issues", "contributors",
            "commits_90d", "releases_90d", "pushed_at", "license", "archived",
        ])
        for cap in snapshot["capabilities"]:
            for i, r in enumerate(cap["rankings"], 1):
                sig = r.get("signals", {})
                w.writerow([
                    cap["slug"], i, r["full_name"], r.get("composite", 0),
                    r.get("maintenance", 0), r.get("popularity", 0),
                    r.get("governance", 0), r.get("license_fit", 0),
                    sig.get("stars", 0), sig.get("forks", 0),
                    sig.get("open_issues", 0), sig.get("contributor_count", 0),
                    sig.get("recent_commit_count_90d", 0),
                    sig.get("recent_release_count_90d", 0),
                    sig.get("pushed_at", ""), sig.get("license_key", ""),
                    sig.get("archived", False),
                ])


# === Entry point =============================================================

def main() -> int:
    ap = argparse.ArgumentParser(description="Build the exo recommend leaderboard.")
    ap.add_argument("--out", default="docs", help="Output directory (default: docs/).")
    ap.add_argument("--weight-profile", default="default",
                    choices=["default", "reliable", "cutting-edge", "commercial"])
    ap.add_argument("--license", default="any",
                    choices=["any", "permissive", "no-agpl", "no-copyleft"],
                    dest="license_constraint")
    ap.add_argument("--from-snapshot", default=None,
                    help="Skip re-fetching; render from an existing data.json.")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out)
    (out_dir / "c").mkdir(parents=True, exist_ok=True)

    if args.from_snapshot:
        with open(args.from_snapshot, "r", encoding="utf-8") as f:
            snapshot = json.load(f)
        print(f"Loaded existing snapshot from {args.from_snapshot}")
    else:
        print(f"Building snapshot (weight_profile={args.weight_profile}, license={args.license_constraint})...")
        snapshot = build_snapshot(
            weight_profile=args.weight_profile,
            license_constraint=args.license_constraint,
            verbose=args.verbose,
        )
        with (out_dir / "data.json").open("w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, default=str)
        _write_csv(snapshot, out_dir / "data.csv")
        print(f"Wrote {out_dir}/data.json + data.csv")

    # Render HTML
    (out_dir / "index.html").write_text(_index_html(snapshot), encoding="utf-8")
    for cap in snapshot["capabilities"]:
        (out_dir / "c" / f"{cap['slug']}.html").write_text(
            _capability_html(snapshot, cap), encoding="utf-8")
    print(f"Wrote {out_dir}/index.html + {len(snapshot['capabilities'])} per-capability pages")
    return 0


if __name__ == "__main__":
    sys.exit(main())
