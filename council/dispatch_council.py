#!/usr/bin/env python3
"""Dispatch sentiment council Run N.

Reads the sealed PROMPT-VARIANTS-SEALED.md, picks the right variant for the
run number, assembles the artifact bundle, computes the deterministic
archetype-to-voice mapping per contract section 3.2, and dispatches 4
parallel LLM calls. Aggregates results and writes the council report.

Usage:
    python dispatch_council.py --run 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
COUNCIL_DIR = ROOT / "council"

ARCHETYPES = [
    {
        "idx": 0,
        "name": "Senior staff engineer",
        "identity": (
            "12+ years in production. Has shipped real systems at scale. Skeptical of hype. "
            "Values simplicity, observability, day-2 ops. Allergic to half-built infra. "
            "Reads READMEs looking for what the project actively avoids saying."
        ),
    },
    {
        "idx": 1,
        "name": "AI researcher",
        "identity": (
            "Publishes at NeurIPS/ICML/EMNLP. Values novelty, mathematical clarity, "
            "citation-quality documentation. Skeptical of 'we wrap existing libraries' "
            "projects without a clear research contribution. Asks 'what is the new idea here?'"
        ),
    },
    {
        "idx": 2,
        "name": "Indie hacker",
        "identity": (
            "Solo founder shipping fast. Building for the next 6 months of revenue, "
            "not the next decade. Values copy-pasteable quickstarts, README-driven "
            "development, low friction. Allergic to enterprise wrappers, kubernetes-first "
            "tooling, and projects with 12 dependencies before 'hello world'."
        ),
    },
    {
        "idx": 3,
        "name": "Homelab self-hoster",
        "identity": (
            "Runs a Proxmox cluster + GPU in the basement. Refuses to send prompts to "
            "OpenAI. Cares deeply about docker-compose simplicity, local-first defaults, "
            "AGPL/MIT-friendly licensing, and 'I can fork this and run forever'. "
            "Skeptical of anything that requires a cloud-provider account."
        ),
    },
]

RUN_CONFIG = {
    1: {
        "variant": 1,
        "voices": [
            {"engine": "codex", "model": "gpt-5.5"},
            {"engine": "gemini", "model": "gemini-2.5-pro"},
            {"engine": "ollama", "model": "nemotron-3-super"},
            {"engine": "ollama", "model": "qwen3-coder:480b"},
        ],
    },
    2: {
        "variant": 2,
        "voices": [
            {"engine": "codex", "model": "gpt-5.5"},
            {"engine": "gemini", "model": "gemini-2.5-pro"},
            {"engine": "ollama", "model": "gpt-oss:120b"},
            {"engine": "ollama", "model": "nemotron-3-super"},
        ],
    },
    3: {
        "variant": 3,
        "voices": [
            {"engine": "codex", "model": "gpt-5.5"},
            {"engine": "gemini", "model": "gemini-2.5-pro"},
            {"engine": "ollama", "model": "qwen3-coder:480b"},
            {"engine": "ollama", "model": "gpt-oss:120b"},
        ],
    },
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_artifact_bundle() -> str:
    """Per AUTONOMY-CONTRACT 3.5: README + Quickstart + WHY + one template + one example."""
    parts = []

    def section(title: str, path: Path, max_lines: int | None = None) -> None:
        if not path.exists():
            return
        text = path.read_text(encoding="utf-8")
        if max_lines:
            text = "\n".join(text.split("\n")[:max_lines])
        parts.append(f"\n\n========== {title} ==========\n{text}")

    section("README.md (root)", ROOT / "README.md", max_lines=400)
    section("Quickstart.md", ROOT / "Quickstart.md")
    section("WHY.md", ROOT / "WHY.md", max_lines=100)
    section("templates/sales-pipeline/README.md", ROOT / "templates" / "sales-pipeline" / "README.md")
    section("templates/sales-pipeline/domain.yaml", ROOT / "templates" / "sales-pipeline" / "domain.yaml")
    section("templates/sales-pipeline/scenario.yaml", ROOT / "templates" / "sales-pipeline" / "scenario.yaml")
    section("examples/sales-pipeline-rehearsal/README.md", ROOT / "examples" / "sales-pipeline-rehearsal" / "README.md")
    section("examples/sales-pipeline-rehearsal/summary.md", ROOT / "examples" / "sales-pipeline-rehearsal" / "summary.md")

    # Add a SHORT snippet of the transcript — first 5 turns, content only
    transcript_path = ROOT / "examples" / "sales-pipeline-rehearsal" / "transcript.jsonl"
    if transcript_path.exists():
        snippet = ["\n\n========== examples/sales-pipeline-rehearsal/transcript.jsonl (first 5 turns) =========="]
        for line in transcript_path.read_text(encoding="utf-8").splitlines()[:6]:
            try:
                obj = json.loads(line)
                aid = obj.get("actor_id", "?")
                role = obj.get("role", "?")
                content = obj.get("content", "")[:500]
                snippet.append(f"\n[Turn {obj.get('turn')}] {aid} ({role}): {content}")
            except json.JSONDecodeError:
                pass
        snippet.append("\n[... 15 more turns truncated for brevity ...]")
        parts.append("\n".join(snippet))

    return "".join(parts)


def load_variant_prompt(variant_num: int) -> str:
    """Read the sealed prompt variants file and extract Variant N."""
    sealed = (COUNCIL_DIR / "PROMPT-VARIANTS-SEALED.md").read_text(encoding="utf-8")
    marker = f"## VARIANT {variant_num}"
    if marker not in sealed:
        raise RuntimeError(f"VARIANT {variant_num} not found in sealed prompts")
    start = sealed.index(marker)
    # Find end: next "## VARIANT" or "## Witness"
    rest = sealed[start + len(marker):]
    next_section = min(
        (rest.find("## VARIANT"), rest.find("## Witness"), rest.find("---")),
        key=lambda i: i if i > 0 else 10**9,
    )
    section = rest[:next_section if next_section > 0 else len(rest)]
    # Extract code block
    if "```" not in section:
        raise RuntimeError(f"No code block in VARIANT {variant_num}")
    after_open = section[section.index("```") + 3:]
    if "```" not in after_open:
        raise RuntimeError(f"Unclosed code block in VARIANT {variant_num}")
    return after_open[: after_open.index("```")].strip()


def render_prompt(template: str, archetype: dict, artifact_bundle: str) -> str:
    return (
        template
        .replace("{{archetype_name}}", archetype["name"])
        .replace("{{archetype_identity}}", archetype["identity"])
        .replace("{{artifact_bundle}}", artifact_bundle)
    )


def call_codex(prompt: str, timeout: int = 240) -> str:
    proc = subprocess.run(
        ["codex", "exec", prompt],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return f"[CODEX ERROR returncode={proc.returncode}]\nstderr:\n{proc.stderr[:2000]}"
    return proc.stdout


def call_gemini(prompt: str, timeout: int = 240) -> str:
    proc = subprocess.run(
        ["gemini", "--approval-mode", "plan", "-p", prompt, "-o", "text"],
        capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return f"[GEMINI ERROR returncode={proc.returncode}]\nstderr:\n{proc.stderr[:2000]}"
    return proc.stdout


def call_ollama_cloud(prompt: str, model: str, timeout: int = 240) -> str:
    key = os.environ.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_CLOUD_API_KEY", "")
    if not key:
        return "[OLLAMA ERROR: no OLLAMA_API_KEY in env]"
    url = "https://ollama.com/api/chat"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.4, "num_predict": 1500},
    }
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        r = requests.post(url, headers=headers, json=body, timeout=timeout)
        if r.status_code != 200:
            return f"[OLLAMA ERROR status={r.status_code}] {r.text[:1000]}"
        return r.json().get("message", {}).get("content", "")
    except Exception as e:
        return f"[OLLAMA EXCEPTION {type(e).__name__}: {e}]"


def dispatch_one_judge(voice: dict, archetype: dict, prompt: str) -> dict:
    """Run a single judge. Returns dict with metadata + response."""
    engine = voice["engine"]
    model = voice["model"]
    t0 = time.time()
    if engine == "codex":
        response = call_codex(prompt)
    elif engine == "gemini":
        response = call_gemini(prompt)
    elif engine == "ollama":
        response = call_ollama_cloud(prompt, model)
    else:
        response = f"[UNKNOWN ENGINE {engine}]"
    return {
        "voice_engine": engine,
        "voice_model": model,
        "archetype": archetype["name"],
        "archetype_idx": archetype["idx"],
        "elapsed_seconds": round(time.time() - t0, 2),
        "raw_response": response,
    }


def extract_judge_json(raw: str) -> dict | None:
    """Try to extract a single JSON object from a judge's response."""
    # Look for the outermost {...}
    start = raw.find("{")
    if start == -1:
        return None
    # Try progressively more text until JSON parses
    depth = 0
    end = start
    for i, c in enumerate(raw[start:], start=start):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    candidate = raw[start:end]
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        # Try removing markdown code fences
        cleaned = candidate.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


REQUIRED_KEYS = {
    "archetype", "first_impression", "biggest_strength", "biggest_weakness",
    "would_star", "would_share", "would_tell_network", "would_NOT_engage",
    "confidence_0_to_10", "what_would_make_me_more_likely_to_engage",
}


def validate_judgment(parsed: dict | None) -> tuple[bool, list[str]]:
    errors = []
    if parsed is None:
        return False, ["could not parse JSON from response"]
    missing = REQUIRED_KEYS - set(parsed.keys())
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    for bool_key in ("would_star", "would_share", "would_tell_network", "would_NOT_engage"):
        if bool_key in parsed and not isinstance(parsed[bool_key], bool):
            errors.append(f"{bool_key} not boolean (was {type(parsed[bool_key]).__name__})")
    if "confidence_0_to_10" in parsed:
        try:
            c = int(parsed["confidence_0_to_10"])
            if not 0 <= c <= 10:
                errors.append(f"confidence out of range: {c}")
        except (TypeError, ValueError):
            errors.append("confidence_0_to_10 not int")
    return len(errors) == 0, errors


def run(run_number: int) -> None:
    cfg = RUN_CONFIG.get(run_number)
    if not cfg:
        # Beyond 3, rotate
        cfg = RUN_CONFIG[((run_number - 1) % 3) + 1]
    variant = cfg["variant"]
    voices = cfg["voices"]

    contract_path = ROOT / "AUTONOMY-CONTRACT.md"
    sealed_path = COUNCIL_DIR / "PROMPT-VARIANTS-SEALED.md"
    contract_sha = sha256_of(contract_path)
    sealed_sha = sha256_of(sealed_path)

    print(f"=== Council Run {run_number} ===")
    print(f"  contract SHA:  {contract_sha}")
    print(f"  sealed SHA:    {sealed_sha}")
    print(f"  prompt variant: {variant}")
    print(f"  voices: {[v['engine']+'/'+v['model'] for v in voices]}")
    print()

    artifact_bundle = load_artifact_bundle()
    print(f"  artifact bundle size: {len(artifact_bundle):,} chars")
    prompt_template = load_variant_prompt(variant)

    # Archetype-to-voice mapping per contract 3.2
    assignments = []
    for vi, voice in enumerate(voices, start=1):
        archetype_idx = (run_number + vi - 1) % 4
        archetype = ARCHETYPES[archetype_idx]
        prompt = render_prompt(prompt_template, archetype, artifact_bundle)
        assignments.append((voice, archetype, prompt))
        print(f"    Voice {vi} ({voice['engine']}/{voice['model']}) → archetype {archetype_idx}: {archetype['name']}")

    # Dispatch all 4 in parallel
    print("\n  Dispatching 4 judges in parallel...")
    results = [None] * 4
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(dispatch_one_judge, v, a, p): i for i, (v, a, p) in enumerate(assignments)}
        for f in as_completed(futures):
            i = futures[f]
            results[i] = f.result()
            r = results[i]
            print(f"    ← Voice {i+1} {r['voice_engine']}/{r['voice_model']} ({r['archetype']}) completed in {r['elapsed_seconds']}s ({len(r['raw_response'])} chars)")

    # Parse + validate
    judgments = []
    for r in results:
        parsed = extract_judge_json(r["raw_response"])
        valid, errors = validate_judgment(parsed)
        judgments.append({
            **r,
            "parsed_judgment": parsed,
            "schema_valid": valid,
            "schema_errors": errors,
        })

    # Aggregate (mechanical only — no Claude judgment)
    pass_count = 0
    star_count = 0
    share_count = 0
    tell_count = 0
    decline_count = 0
    confidences = []
    for j in judgments:
        p = j["parsed_judgment"]
        if not j["schema_valid"] or not p:
            continue
        if p.get("would_star") is True: star_count += 1
        if p.get("would_share") is True: share_count += 1
        if p.get("would_tell_network") is True: tell_count += 1
        if p.get("would_NOT_engage") is True: decline_count += 1
        try:
            confidences.append(int(p.get("confidence_0_to_10", 0)))
        except (TypeError, ValueError):
            pass
        if (p.get("would_star") is True
            and p.get("would_share") is True
            and p.get("would_tell_network") is True
            and not p.get("would_NOT_engage")):
            pass_count += 1

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    schema_failures = sum(1 for j in judgments if not j["schema_valid"])

    run_passed = (
        pass_count == 4
        and decline_count == 0
        and avg_confidence >= 7
        and schema_failures == 0
    )

    report = {
        "run_number": run_number,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "contract_sha": contract_sha,
        "sealed_prompts_sha": sealed_sha,
        "variant": variant,
        "voices": voices,
        "judgments": judgments,
        "summary": {
            "would_star_count": star_count,
            "would_share_count": share_count,
            "would_tell_network_count": tell_count,
            "would_NOT_engage_count": decline_count,
            "schema_validation_failures": schema_failures,
            "passing_archetypes_count": pass_count,
            "average_confidence": round(avg_confidence, 2),
            "run_passed": run_passed,
        },
    }

    out_path = COUNCIL_DIR / f"RUN-{run_number:02d}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"=== Run {run_number} {'PASSED' if run_passed else 'FAILED'} ===")
    print(f"  would_star:           {star_count}/4")
    print(f"  would_share:          {share_count}/4")
    print(f"  would_tell_network:   {tell_count}/4")
    print(f"  would_NOT_engage:     {decline_count}/4")
    print(f"  schema_failures:      {schema_failures}/4")
    print(f"  avg_confidence:       {avg_confidence:.1f}/10")
    print(f"  passing_archetypes:   {pass_count}/4")
    print()
    print(f"  Report: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=int, required=True, help="Run number (1, 2, 3, ...)")
    args = parser.parse_args()
    run(args.run)
