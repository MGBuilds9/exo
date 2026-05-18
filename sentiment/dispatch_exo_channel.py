#!/usr/bin/env python3
"""Dispatch an exo-based sentiment channel.

Takes a channel directory containing domain.yaml + scenario.yaml,
injects the ARTIFACT-BUNDLE-rc1.txt into the scenario's initial_context,
swaps actor models to ollama-cloud/qwen3-coder:480b, runs exo, writes
report.

Usage:
    python sentiment/dispatch_exo_channel.py <channel_dir>
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

import yaml

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = (ROOT / "sentiment" / "ARTIFACT-BUNDLE-rc1.txt").read_text(encoding="utf-8")


def prepare_runtime(channel_dir: Path) -> Path:
    src_dom = channel_dir / "domain.yaml"
    src_sce = channel_dir / "scenario.yaml"
    runtime = channel_dir / "runtime"
    runtime.mkdir(exist_ok=True)

    d = yaml.safe_load(src_dom.read_text(encoding="utf-8"))
    s = yaml.safe_load(src_sce.read_text(encoding="utf-8"))

    # Inject artifact bundle into initial_context
    existing = s.get("initial_context", "")
    s["initial_context"] = (
        existing
        + "\n\n---\nARTIFACT BUNDLE (read this before commenting; quote specific sections):\n"
        + BUNDLE
    )

    # Swap all actor models to ollama-cloud (claude-oauth shell-out untested in v0.1)
    for a in d.get("actors", []):
        a["model"] = "ollama-cloud/qwen3-coder:480b"
    d["runtime"]["default_model"] = "ollama-cloud/qwen3-coder:480b"

    (runtime / "domain.yaml").write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (runtime / "scenario.yaml").write_text(yaml.safe_dump(s, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return runtime


def run_channel(channel_dir: Path) -> dict:
    runtime = prepare_runtime(channel_dir)
    out_dir = channel_dir / "run"
    if out_dir.exists():
        import shutil
        shutil.rmtree(out_dir)
    print(f"=== Running {channel_dir.name} ===")
    rc = subprocess.run(
        ["python", str(ROOT / "exo"), "run",
         str(runtime / "domain.yaml"),
         "--scenario", str(runtime / "scenario.yaml"),
         "--out", str(out_dir)],
        cwd=str(ROOT),
        timeout=1500,
    ).returncode
    return {"channel": channel_dir.name, "runner_returncode": rc, "out": str(out_dir)}


def analyze(channel_dir: Path) -> dict:
    out_dir = channel_dir / "run"
    transcript = out_dir / "transcript.jsonl"
    if not transcript.exists():
        return {"error": "no transcript", "channel": channel_dir.name}
    turns = [json.loads(l) for l in transcript.read_text(encoding="utf-8").splitlines() if l.strip()]
    actor_turns = [t for t in turns if t.get("actor_id") != "narrator"]
    by_actor = {}
    for t in actor_turns:
        aid = t["actor_id"]
        sigs = t.get("signals") or {}
        for k, v in sigs.items():
            if isinstance(v, (int, float)):
                by_actor.setdefault((aid, k), []).append(v)
    # Per-actor mean per signal
    aggregated = {}
    for (aid, k), vals in by_actor.items():
        aggregated.setdefault(aid, {})[k] = {
            "mean": round(sum(vals) / len(vals), 2),
            "min": min(vals), "max": max(vals), "n": len(vals),
        }
    return {
        "channel": channel_dir.name,
        "total_turns": len(actor_turns),
        "by_actor": aggregated,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: dispatch_exo_channel.py <channel_dir>")
        sys.exit(2)
    channel_dir = Path(sys.argv[1]).resolve()
    if not channel_dir.exists():
        print(f"no such directory: {channel_dir}")
        sys.exit(2)
    dispatch_result = run_channel(channel_dir)
    print(json.dumps(dispatch_result, indent=2))
    analysis = analyze(channel_dir)
    (channel_dir / "ANALYSIS.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    print("\n=== ANALYSIS ===")
    print(json.dumps(analysis, indent=2))


if __name__ == "__main__":
    main()
