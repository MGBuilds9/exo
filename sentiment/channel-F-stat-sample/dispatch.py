#!/usr/bin/env python3
"""Channel F — n=20 statistical sample.

5 invocations per archetype x 4 archetypes = 20 LLM-as-archetype-judge
invocations, fresh sessions, against the rc1 artifact bundle.

Pass criterion: >= 16/20 (80%) return would_star + would_share + would_tell.

Uses Ollama Cloud (qwen3-coder:480b) with temperature variation across the
5 invocations per archetype to introduce healthy variance.
"""
from __future__ import annotations

import json
import os
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


ARCHETYPES = [
    {
        "name": "Senior staff engineer",
        "identity": "12+ years production. Skeptical of hype. Values simplicity, observability, day-2 ops. Allergic to half-built infra.",
    },
    {
        "name": "Open-source maintainer evaluating for adoption",
        "identity": "Maintains a popular OSS project. Evaluates new tools to adopt. Cares about license, README quality, install friction, governance signals, day-2 ops.",
    },
    {
        "name": "Indie hacker",
        "identity": "Solo founder shipping fast. Values copy-pasteable quickstarts, low friction. Allergic to enterprise wrappers and projects with 12 deps before hello world.",
    },
    {
        "name": "Homelab self-hoster",
        "identity": "Proxmox + GPU. Refuses to send prompts to OpenAI. Cares about docker-compose simplicity, local-first defaults, AGPL/MIT-friendly licensing.",
    },
]


def build_prompt(archetype_name: str, archetype_identity: str) -> str:
    """Build by string concatenation, NOT .format() — the artifact bundle
    contains '{"service": ...}' JSON snippets that .format() would treat as
    format placeholders and raise KeyError.
    """
    return (
        "You are a blind evaluator. Your assigned archetype: " + archetype_name + ".\n\n"
        "Your identity: " + archetype_identity + "\n\n"
        "You are reading the artifact bundle below for the first time. Decide honestly whether you would (a) star this on GitHub, (b) share it on professional channels, (c) tell your network about it. Decline is honest signal — do not feel compelled to engage.\n\n"
        "Return exactly ONE JSON object, no preamble:\n"
        "{\n"
        '  "archetype": "' + archetype_name + '",\n'
        '  "first_impression": "<one sentence>",\n'
        '  "biggest_strength": "<one sentence>",\n'
        '  "biggest_weakness": "<one sentence>",\n'
        '  "would_star": true | false,\n'
        '  "would_share": true | false,\n'
        '  "would_tell_network": true | false,\n'
        '  "confidence_0_to_10": <int>\n'
        "}\n\n"
        "ARTIFACT BUNDLE:\n"
        + BUNDLE
    )


def call_ollama(prompt: str, temperature: float, timeout: int = 240) -> str:
    key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_CLOUD_API_KEY", "")
    if not key:
        return "[NO OLLAMA KEY]"
    r = requests.post(
        "https://ollama.com/api/chat",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": "qwen3-coder:480b",
              "messages": [{"role": "user", "content": prompt}],
              "stream": False,
              "options": {"temperature": temperature, "num_predict": 800, "num_ctx": 32768}},
        timeout=timeout,
    )
    if r.status_code != 200:
        return f"[OLLAMA ERROR {r.status_code}: {r.text[:300]}]"
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


def judge(archetype: dict, sample_index: int) -> dict:
    t0 = time.time()
    # Temperature variation: 0.3, 0.4, 0.5, 0.6, 0.7 across 5 samples per archetype
    temp = 0.3 + 0.1 * sample_index
    prompt = build_prompt(archetype["name"], archetype["identity"])
    raw = call_ollama(prompt, temp)
    parsed = extract_json(raw)
    return {
        "archetype": archetype["name"],
        "sample_index": sample_index,
        "temperature": temp,
        "elapsed_seconds": round(time.time() - t0, 2),
        "parsed": parsed,
        "raw_excerpt": raw[:300] if not parsed else None,
    }


def main():
    print("Channel F — n=20 statistical sample (5 per archetype x 4 archetypes)")
    print("Pass criterion: >= 16/20 (80%) return would_star + would_share + would_tell")
    print()

    jobs = []
    for arch in ARCHETYPES:
        for i in range(5):
            jobs.append((arch, i))

    results = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(judge, a, i): (a["name"], i) for a, i in jobs}
        for f in as_completed(futures):
            r = f.result()
            results.append(r)
            p = r.get("parsed")
            if p:
                stars = (p.get("would_star"), p.get("would_share"), p.get("would_tell_network"))
                print(f"  [{r['archetype'][:35]:35s} #{r['sample_index']}, T={r['temperature']:.1f}, {r['elapsed_seconds']}s] star/share/tell = {stars}, conf={p.get('confidence_0_to_10')}")
            else:
                print(f"  [{r['archetype'][:35]:35s} #{r['sample_index']}, T={r['temperature']:.1f}, {r['elapsed_seconds']}s] SCHEMA INVALID")

    # Aggregate
    parsed_count = sum(1 for r in results if r["parsed"])
    full_pass_count = 0
    star_count = 0
    share_count = 0
    tell_count = 0
    confidences = []
    for r in results:
        p = r["parsed"]
        if not p:
            continue
        if p.get("would_star"): star_count += 1
        if p.get("would_share"): share_count += 1
        if p.get("would_tell_network"): tell_count += 1
        if p.get("would_star") and p.get("would_share") and p.get("would_tell_network"):
            full_pass_count += 1
        try:
            confidences.append(int(p.get("confidence_0_to_10", 0)))
        except (TypeError, ValueError):
            pass

    # Per-archetype breakdown
    per_arch = {}
    for r in results:
        p = r.get("parsed")
        if not p:
            continue
        a = r["archetype"]
        per_arch.setdefault(a, {"n": 0, "stars": 0, "shares": 0, "tells": 0, "full": 0})
        per_arch[a]["n"] += 1
        if p.get("would_star"): per_arch[a]["stars"] += 1
        if p.get("would_share"): per_arch[a]["shares"] += 1
        if p.get("would_tell_network"): per_arch[a]["tells"] += 1
        if p.get("would_star") and p.get("would_share") and p.get("would_tell_network"):
            per_arch[a]["full"] += 1

    print()
    print("=== PER-ARCHETYPE BREAKDOWN ===")
    for a, d in sorted(per_arch.items()):
        print(f"  {a:40s}  n={d['n']}/5, stars={d['stars']}, shares={d['shares']}, tells={d['tells']}, FULL={d['full']}")
    print()
    print("=== AGGREGATE ===")
    print(f"  parsed_count:    {parsed_count}/20")
    print(f"  would_star:      {star_count}/20")
    print(f"  would_share:     {share_count}/20")
    print(f"  would_tell:      {tell_count}/20")
    print(f"  FULL pass:       {full_pass_count}/20")
    print(f"  avg confidence:  {sum(confidences)/max(1,len(confidences)):.1f}/10")

    passed = full_pass_count >= 16
    print(f"\nPass criterion: >=16/20 full-pass  =>  {'PASSED' if passed else 'FAILED'}")

    out = {
        "results": results,
        "per_archetype": per_arch,
        "summary": {
            "parsed_count": parsed_count,
            "star_count": star_count,
            "share_count": share_count,
            "tell_count": tell_count,
            "full_pass_count": full_pass_count,
            "avg_confidence": round(sum(confidences)/max(1, len(confidences)), 2),
            "passed": passed,
        },
    }
    out_path = Path(__file__).resolve().parent / "REPORT.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nReport: {out_path}")


if __name__ == "__main__":
    main()
