#!/usr/bin/env python3
"""Pull a corpus of recently-viral repos for README + metadata analysis.

Strategy: multiple gh search queries covering different axes that exo
sits at (AI/LLM/agent, dev tools, YAML-config, multi-agent sim).
Dedupe. Pull README + metadata for each. Persist for downstream
analysis.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

OUT = Path(__file__).resolve().parent
CORPUS = OUT / "corpus"
CORPUS.mkdir(exist_ok=True)


SEARCH_QUERIES = [
    # Axis 1: AI / LLM / agent (Python), recently viral
    {"q": "llm agent", "created": ">2026-02-01", "stars": ">500", "language": "python", "limit": 30},
    {"q": "ai assistant", "created": ">2026-02-01", "stars": ">800", "language": "python", "limit": 20},
    # Axis 2: dev tools / CLI in Python or TypeScript
    {"q": "developer tool", "created": ">2026-02-01", "stars": ">500", "language": "python", "limit": 15},
    {"q": "cli tool", "created": ">2026-02-01", "stars": ">500", "language": "typescript", "limit": 15},
    # Axis 3: multi-agent / simulation
    {"q": "multi-agent", "created": ">2026-01-01", "stars": ">300", "language": "python", "limit": 20},
    {"q": "simulation framework", "created": ">2026-01-01", "stars": ">300", "language": "python", "limit": 15},
    # Axis 4: docker-compose / self-hostable AI
    {"q": "self-hosted ai", "created": ">2026-01-01", "stars": ">500", "limit": 15},
    # Axis 5: agent framework specifically
    {"q": "agent framework", "created": ">2025-12-01", "stars": ">1000", "language": "python", "limit": 15},
]


def run_gh_search(query: dict) -> list[dict]:
    cmd = [
        "gh", "search", "repos", query["q"],
        "--created", query["created"],
        "--stars", query["stars"],
        "--limit", str(query["limit"]),
        "--json", "name,owner,description,stargazersCount,createdAt,license,url,language,forksCount,openIssuesCount",
    ]
    if "language" in query:
        cmd.extend(["--language", query["language"]])
    try:
        out = subprocess.check_output(cmd, text=True, encoding="utf-8", errors="replace", timeout=30)
        return json.loads(out)
    except subprocess.CalledProcessError as e:
        print(f"  ERROR for {query}: {e}")
        return []
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT for {query}")
        return []


def fetch_readme(owner: str, name: str) -> str | None:
    """Pull README via gh api. Try README.md, then any README variant."""
    for candidate in ("README.md", "Readme.md", "readme.md", "README", "README.rst"):
        try:
            out = subprocess.check_output(
                ["gh", "api", f"/repos/{owner}/{name}/contents/{candidate}",
                 "--jq", ".content"],
                text=True, encoding="utf-8", errors="replace", timeout=20,
                stderr=subprocess.DEVNULL,
            )
            content_b64 = out.strip()
            if content_b64:
                import base64
                try:
                    return base64.b64decode(content_b64).decode("utf-8", errors="replace")
                except Exception:
                    continue
        except subprocess.CalledProcessError:
            continue
        except subprocess.TimeoutExpired:
            return None
    return None


def main():
    all_repos: dict[str, dict] = {}
    print(f"Running {len(SEARCH_QUERIES)} gh search queries...")
    for i, q in enumerate(SEARCH_QUERIES, 1):
        print(f"  [{i}/{len(SEARCH_QUERIES)}] q={q['q']!r} lang={q.get('language','*')} stars>{q['stars']}")
        results = run_gh_search(q)
        for r in results:
            full_name = f"{r['owner']['login']}/{r['name']}"
            if full_name not in all_repos:
                all_repos[full_name] = r
        time.sleep(1)  # be polite

    print(f"\nDedup: {len(all_repos)} unique repos in corpus")

    # Sort by stars desc
    sorted_repos = sorted(all_repos.values(), key=lambda r: -r["stargazersCount"])

    # Pull README for top N
    N = min(40, len(sorted_repos))
    print(f"\nPulling READMEs for top {N} (by stars)...")
    enriched = []
    for i, repo in enumerate(sorted_repos[:N], 1):
        owner = repo["owner"]["login"]
        name = repo["name"]
        print(f"  [{i}/{N}] {owner}/{name} ({repo['stargazersCount']} stars, {repo.get('language','?')})")
        readme = fetch_readme(owner, name)
        if readme:
            repo["readme"] = readme
            repo["readme_length"] = len(readme)
            enriched.append(repo)
        else:
            print(f"    (no README pulled)")
        time.sleep(0.5)

    # Persist
    out_path = OUT / "corpus.json"
    out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {len(enriched)} enriched repos to {out_path}")

    # Quick stats
    print("\n=== Quick stats ===")
    print(f"Star range: {min(r['stargazersCount'] for r in enriched)} – {max(r['stargazersCount'] for r in enriched)}")
    print(f"Avg readme length: {sum(r.get('readme_length',0) for r in enriched) // len(enriched):,} chars")
    print(f"License distribution:")
    licenses = {}
    for r in enriched:
        lic = (r.get("license") or {}).get("key", "no-license")
        licenses[lic] = licenses.get(lic, 0) + 1
    for lic, n in sorted(licenses.items(), key=lambda x: -x[1]):
        print(f"  {lic:25s} {n}")
    print(f"\nLanguage distribution:")
    langs = {}
    for r in enriched:
        l = r.get("language") or "unknown"
        langs[l] = langs.get(l, 0) + 1
    for l, n in sorted(langs.items(), key=lambda x: -x[1]):
        print(f"  {l:25s} {n}")


if __name__ == "__main__":
    main()
