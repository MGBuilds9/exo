#!/usr/bin/env python3
"""Channel E — adversarial council ("find errors, don't validate").

Inspired by gstack's /llm-council-adversarial skill: 4 distinct LLM voices
asked to FIND failures in the artifact, not validate it. The trick is the
framing — "find errors" produces signal; "is this right?" produces compliance.

After listing failures, each voice judges: would a power user star this
DESPITE the flaws you found?

Pass criterion: 4/4 voices say `would_star_despite_flaws: true` AND
flaws-found are not catastrophic (i.e., none of: 'this doesn't actually run',
'license-incompatible', 'data-leakage risk').
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

ROOT = Path(__file__).resolve().parent.parent.parent
BUNDLE = (ROOT / "sentiment" / "ARTIFACT-BUNDLE-rc2.txt").read_text(encoding="utf-8")


ADVERSARIAL_PROMPT = """You are an adversarial reviewer. Your job is NOT to validate this artifact. Your job is to FIND FAILURES in it.

Read the artifact bundle below carefully. Identify at least 3 concrete failure modes — specific things in the README claims that don't hold up, examples that don't substantiate the pitch, gaps between marketing voice and engineering reality, architectural decisions that will break at scale, license/governance issues, security concerns, anything else.

DO NOT be polite. DO NOT hedge with "but overall this is interesting." Surface the failures directly.

After you've listed at least 3 failures, answer one question: knowing these failures, would a power user (senior staff engineer, OSS maintainer evaluating for adoption, indie hacker, homelab self-hoster) still STAR this on GitHub? You may say yes OR no. There is no compliance pressure either way.

Return EXACTLY one JSON object, no preamble or trailing prose:

{
  "failures_found": [
    "<specific failure 1: what claim doesn't hold up and why>",
    "<specific failure 2>",
    "<specific failure 3>",
    "<more if you see them>"
  ],
  "catastrophic_failure_present": true | false,
  "catastrophic_failure_detail": "<one sentence if true, else empty>",
  "would_star_despite_flaws": true | false,
  "reasoning_for_star_decision": "<one sentence — your honest reasoning>",
  "confidence_0_to_10": <int>
}

ARTIFACT BUNDLE:
""" + BUNDLE


def call_codex(prompt: str, timeout: int = 240) -> str:
    codex = shutil.which("codex") or shutil.which("codex.cmd")
    if not codex:
        return "[CODEX not in PATH]"
    p = subprocess.run([codex, "exec", "-"], input=prompt, capture_output=True,
                       text=True, timeout=timeout, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        return f"[CODEX ERROR {p.returncode}: {p.stderr[:500]}]"
    return p.stdout


def call_gemini(prompt: str, timeout: int = 240) -> str:
    gemini = shutil.which("gemini") or shutil.which("gemini.cmd")
    if not gemini:
        return "[GEMINI not in PATH]"
    p = subprocess.run([gemini, "--approval-mode", "plan", "-o", "text",
                        "-p", "Read stdin and respond per its instructions."],
                       input=prompt, capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        return f"[GEMINI ERROR {p.returncode}: {p.stderr[:500]}]"
    return p.stdout


def call_ollama(prompt: str, model: str, timeout: int = 240) -> str:
    key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_CLOUD_API_KEY", "")
    if not key:
        return "[NO OLLAMA KEY]"
    r = requests.post(
        "https://ollama.com/api/chat",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "stream": False,
              "options": {"temperature": 0.3, "num_predict": 2000, "num_ctx": 32768}},
        timeout=timeout,
    )
    if r.status_code != 200:
        return f"[OLLAMA ERROR {r.status_code}: {r.text[:500]}]"
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


def judge_one(name: str, fn) -> dict:
    t0 = time.time()
    raw = fn(ADVERSARIAL_PROMPT)
    parsed = extract_json(raw)
    return {
        "voice": name,
        "elapsed_seconds": round(time.time() - t0, 2),
        "parsed": parsed,
        "raw_excerpt": raw[:500] if not parsed else None,
    }


def main():
    print("Channel E — adversarial council ('find errors, don't validate')")
    print("Voices: codex / gemini / ollama-cloud:qwen3-coder / ollama-cloud:gpt-oss:120b")
    print()
    voices = {
        "codex": lambda p: call_codex(p),
        "gemini": lambda p: call_gemini(p),
        "ollama-qwen3": lambda p: call_ollama(p, "qwen3-coder:480b"),
        "ollama-gpt-oss": lambda p: call_ollama(p, "gpt-oss:120b"),
    }

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(judge_one, name, fn): name for name, fn in voices.items()}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            if r["parsed"]:
                p = r["parsed"]
                stars = p.get("would_star_despite_flaws")
                catastrophic = p.get("catastrophic_failure_present")
                n_failures = len(p.get("failures_found", []))
                print(f"  {r['voice']:18s} ({r['elapsed_seconds']}s): found {n_failures} failures, catastrophic={catastrophic}, star={stars}")
            else:
                print(f"  {r['voice']:18s} ({r['elapsed_seconds']}s): SCHEMA INVALID")

    # Aggregate
    parsed_count = sum(1 for r in results if r["parsed"])
    star_count = sum(1 for r in results if r["parsed"] and r["parsed"].get("would_star_despite_flaws"))
    catastrophic_count = sum(1 for r in results if r["parsed"] and r["parsed"].get("catastrophic_failure_present"))
    total_failures = sum(len(r["parsed"].get("failures_found", [])) for r in results if r["parsed"])

    print()
    print("=== AGGREGATE ===")
    print(f"  parsed_count:       {parsed_count}/4")
    print(f"  star_count:         {star_count}/4")
    print(f"  catastrophic_count: {catastrophic_count}/4 (must be 0 for pass)")
    print(f"  total_failures:     {total_failures}")

    passed = star_count == 4 and catastrophic_count == 0 and parsed_count == 4
    print(f"\n  Pass criterion: 4/4 star + 0 catastrophic + 0 schema fail  =>  {'PASSED' if passed else 'FAILED'}")

    out = {
        "results": results,
        "summary": {
            "parsed_count": parsed_count,
            "star_count": star_count,
            "catastrophic_count": catastrophic_count,
            "total_failures": total_failures,
            "passed": passed,
        },
    }
    out_path = Path(__file__).resolve().parent / "REPORT.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
