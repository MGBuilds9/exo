#!/usr/bin/env python3
"""Extract structural patterns from the viral-repo corpus.

Outputs ANALYSIS.md with stats + patterns + concrete deltas to apply to
exo's README.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent
corpus = json.loads((ROOT / "corpus.json").read_text(encoding="utf-8"))


def extract_section_headings(readme: str) -> list[str]:
    return re.findall(r"^#{1,3}\s+(.+?)$", readme, flags=re.MULTILINE)


def first_paragraph(readme: str) -> str:
    """First paragraph after the title."""
    lines = readme.split("\n")
    # Skip frontmatter / images / badges / title
    started = False
    para = []
    for line in lines:
        stripped = line.strip()
        if not started:
            # Look for start: a content line that isn't a heading, badge, image, or div
            if stripped and not stripped.startswith(("#", "<", "![", "[!", "---", "|", "```")):
                started = True
                para.append(stripped)
        else:
            if not stripped:
                if para:
                    break
            elif stripped.startswith(("#", "<", "```")):
                break
            else:
                para.append(stripped)
    return " ".join(para)


def count_badges(readme: str) -> int:
    return len(re.findall(r"\[!\[", readme))


def has_image_or_gif(readme: str) -> bool:
    return bool(re.search(r"!\[.*?\]\(.*?\.(gif|png|jpg|jpeg|webp|svg|mp4)\)", readme, re.IGNORECASE))


def has_quickstart(readme: str) -> bool:
    return bool(re.search(r"^#{1,3}\s*(quickstart|quick start|installation|install|getting started)", readme, re.MULTILINE | re.IGNORECASE))


def code_block_count(readme: str) -> int:
    return len(re.findall(r"^```", readme, flags=re.MULTILINE)) // 2


def has_comparison_table(readme: str) -> bool:
    return bool(re.search(r"\|.*?\|.*?\|", readme))


def first_h1(readme: str) -> str | None:
    m = re.search(r"^#\s+(.+?)$", readme, flags=re.MULTILINE)
    return m.group(1).strip() if m else None


# === Compute per-repo stats ===

records = []
for r in corpus:
    readme = r.get("readme", "")
    if not readme:
        continue
    h = extract_section_headings(readme)
    records.append({
        "full_name": f"{r['owner']['login']}/{r['name']}",
        "stars": r["stargazersCount"],
        "language": r.get("language"),
        "license": (r.get("license") or {}).get("key", ""),
        "readme_chars": len(readme),
        "readme_lines": len(readme.split("\n")),
        "n_sections": len(h),
        "headings": h,
        "first_paragraph": first_paragraph(readme),
        "first_h1": first_h1(readme),
        "n_badges": count_badges(readme),
        "has_image": has_image_or_gif(readme),
        "has_quickstart": has_quickstart(readme),
        "n_code_blocks": code_block_count(readme),
        "has_table": has_comparison_table(readme),
        "description": r.get("description", ""),
    })


# === Aggregate stats ===

def s(field, label, formatter=None):
    vals = [r[field] for r in records if r.get(field) is not None]
    if not vals: return
    if isinstance(vals[0], bool):
        true_n = sum(vals)
        return f"  {label:30s}  {true_n}/{len(vals)} ({100*true_n/len(vals):.0f}%)"
    if isinstance(vals[0], (int, float)):
        return f"  {label:30s}  min={min(vals)} max={max(vals)} med={statistics.median(vals):.0f} mean={statistics.mean(vals):.0f}"
    return None


print("=" * 70)
print(f"VIRAL REPO ANALYSIS — n={len(records)}")
print("=" * 70)
print()
print("README structure:")
print(s("readme_chars", "README length (chars)"))
print(s("readme_lines", "README length (lines)"))
print(s("n_sections", "Number of H1/H2/H3 sections"))
print(s("n_badges", "Number of badges"))
print(s("n_code_blocks", "Number of fenced code blocks"))
print(s("has_image", "Has image/gif/video"))
print(s("has_quickstart", "Has Quickstart/Install section"))
print(s("has_table", "Has comparison/feature table"))
print()

# Most common section headings (normalized)
all_headings = []
for r in records:
    for h in r["headings"]:
        # Normalize: lowercase, strip emojis/punctuation
        norm = re.sub(r"[^\w\s]", "", h.lower()).strip()
        if norm:
            all_headings.append(norm)

print("Top 20 section headings across corpus:")
for heading, count in Counter(all_headings).most_common(20):
    pct = 100 * count / len(records)
    print(f"  {heading[:50]:50s}  {count}/{len(records)} ({pct:.0f}%)")
print()

# License distribution
print("License distribution:")
for lic, n in Counter(r["license"] for r in records).most_common():
    print(f"  {lic or 'none':25s}  {n}")
print()

# Tagline / first paragraph samples
print("Sample taglines (top 10 by stars):")
sorted_records = sorted(records, key=lambda r: -r["stars"])
for r in sorted_records[:10]:
    desc = (r["description"] or "")[:120]
    print(f"  [{r['stars']:>5}] {r['full_name']}: {desc}")
print()

# Sample first paragraphs
print("First paragraphs (top 5 by stars):")
for r in sorted_records[:5]:
    para = r["first_paragraph"][:300]
    print(f"  [{r['stars']:>5}] {r['full_name']}:")
    print(f"    {para}")
    print()

# Compare to exo's README
exo_readme_path = ROOT.parent.parent / "README.md"
if exo_readme_path.exists():
    exo = exo_readme_path.read_text(encoding="utf-8")
    print("=" * 70)
    print("EXO COMPARISON (rc3)")
    print("=" * 70)
    print(f"  exo README chars: {len(exo)}  vs corpus median {statistics.median(r['readme_chars'] for r in records):.0f}")
    print(f"  exo README lines: {len(exo.split(chr(10)))}  vs corpus median {statistics.median(r['readme_lines'] for r in records):.0f}")
    print(f"  exo section count: {len(extract_section_headings(exo))}  vs corpus median {statistics.median(r['n_sections'] for r in records):.0f}")
    print(f"  exo badges: {count_badges(exo)}  vs corpus median {statistics.median(r['n_badges'] for r in records):.0f}")
    print(f"  exo code blocks: {code_block_count(exo)}  vs corpus median {statistics.median(r['n_code_blocks'] for r in records):.0f}")
    print(f"  exo has image/gif: {has_image_or_gif(exo)}  vs corpus {sum(r['has_image'] for r in records)}/{len(records)}")
    print(f"  exo has table: {has_comparison_table(exo)}")
    print(f"  exo first H1: {first_h1(exo)}")
    print(f"  exo first paragraph: {first_paragraph(exo)[:400]}")

# Persist for LLM synthesis step
records_summary = [{k: v for k, v in r.items() if k != "headings"} for r in records]
(ROOT / "analysis-data.json").write_text(json.dumps({
    "n_repos": len(records),
    "records": records_summary,
    "section_heading_frequency": dict(Counter(all_headings).most_common(40)),
}, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\nFull data: {ROOT / 'analysis-data.json'}")
