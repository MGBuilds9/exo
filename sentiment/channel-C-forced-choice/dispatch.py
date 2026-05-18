#!/usr/bin/env python3
"""Channel C — forced-choice comparative judgment.

For each of 10 use cases, dispatch an LLM-as-judge that sees the case
description + 5 candidate tool descriptions, must pick ONE with a 100-word
defense. Tallies wins per tool.

Pass criterion: exo wins >=4 of 10.

Uses Ollama Cloud directly (one model: qwen3-coder:480b) — no exo runtime.
"""
from __future__ import annotations

import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
import yaml

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent
CASES = yaml.safe_load((ROOT / "cases.yaml").read_text(encoding="utf-8"))


def render_prompt(case: dict, tools: list[dict]) -> str:
    tool_block = "\n".join(f"- **{t['name']}**: {t['one_liner']}" for t in tools)
    return f"""You are a senior AI engineering practitioner choosing the right tool for a real problem.

THE PROBLEM:
{case['description']}

CANDIDATE TOOLS:
{tool_block}

YOUR TASK:
Pick exactly ONE tool. Defend the choice in 80-120 words. Be specific about why this tool fits the problem better than each of the other four. Do NOT hedge. Do NOT pick more than one.

Format your response as exactly one JSON object, no preamble:

{{
  "chosen_tool": "<name from the candidate list>",
  "defense": "<80-120 words on why THIS tool, in contrast to the other four>",
  "second_best": "<name>",
  "biggest_concern_about_chosen": "<one sentence>"
}}
"""


def call_ollama_cloud(prompt: str, timeout: int = 120) -> str:
    key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_CLOUD_API_KEY", "")
    if not key:
        return "[NO OLLAMA KEY]"
    r = requests.post(
        "https://ollama.com/api/chat",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "qwen3-coder:480b",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "options": {"temperature": 0.3, "num_predict": 500, "num_ctx": 8192},
        },
        timeout=timeout,
    )
    if r.status_code != 200:
        return f"[OLLAMA ERROR {r.status_code}: {r.text[:200]}]"
    return r.json().get("message", {}).get("content", "")


def extract_json(text: str) -> dict | None:
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i, c in enumerate(text[start:], start=start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def judge_one_case(case: dict) -> dict:
    t0 = time.time()
    prompt = render_prompt(case, CASES["candidate_tools"])
    response = call_ollama_cloud(prompt)
    parsed = extract_json(response)
    return {
        "case_id": case["id"],
        "elapsed_seconds": round(time.time() - t0, 2),
        "chosen_tool": parsed.get("chosen_tool", "[UNPARSED]") if parsed else "[UNPARSED]",
        "second_best": parsed.get("second_best", "?") if parsed else "?",
        "defense": parsed.get("defense", "") if parsed else "",
        "concern": parsed.get("biggest_concern_about_chosen", "") if parsed else "",
        "raw": response if not parsed else None,
    }


def main():
    print(f"Channel C — forced-choice comparative ({len(CASES['cases'])} cases)")
    print(f"Candidates: {[t['name'] for t in CASES['candidate_tools']]}")
    print()
    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(judge_one_case, c): c["id"] for c in CASES["cases"]}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            print(f"  {r['case_id']:35s} -> {r['chosen_tool']:15s} (2nd: {r['second_best']:15s}, {r['elapsed_seconds']}s)")

    # Tally
    tally = {}
    for r in results:
        tally[r["chosen_tool"]] = tally.get(r["chosen_tool"], 0) + 1
    print()
    print("=== TALLY ===")
    for tool, n in sorted(tally.items(), key=lambda x: -x[1]):
        print(f"  {tool:20s}  {n}/{len(results)}")

    exo_wins = tally.get("exo", 0)
    passed = exo_wins >= 4
    print()
    print(f"exo wins: {exo_wins}/{len(results)}  (pass criterion: >=4)  =>  {'PASSED' if passed else 'FAILED'}")

    out = {"results": sorted(results, key=lambda r: r["case_id"]),
           "tally": tally, "exo_wins": exo_wins, "passed": passed,
           "n_cases": len(results)}
    (ROOT / "REPORT.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {ROOT / 'REPORT.json'}")


if __name__ == "__main__":
    main()
