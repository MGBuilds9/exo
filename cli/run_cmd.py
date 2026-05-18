"""exo run — execute a multi-agent simulation defined by domain.yaml + scenario.yaml.

v0.1 runtime is intentionally simple:
- Read domain (actors + memory + model) and scenario (trigger + turns + signals)
- For each turn, each actor speaks in sequence
- Each actor's "speak" is an LLM call with their persona as system prompt and the
  full conversation so far as context, plus a request to emit signal values.
- All output writes to a single transcript.jsonl + a final summary.

No graph/vector storage in v0.1 — that comes when system_kind requires it (next
iteration). The architecture supports it; the runtime delegates to the storage
modules when configured.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from exo_runtime.llm_router import LLMRouter, LLMRequest
from exo_runtime.signal_extractor import extract_signals

console = Console()


def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_actor_system_prompt(actor: dict, domain: dict, scenario: dict, signal_names: list[str]) -> str:
    return f"""You are playing a character in a multi-agent simulation.

CHARACTER ID: {actor['id']}
ROLE: {actor['role']}
PERSONA: {actor['persona']}

SIMULATION CONTEXT:
{scenario.get('initial_context', '')}

TRIGGER EVENT:
{scenario.get('trigger', '')}

INSTRUCTIONS:
- Stay in character. Speak as this character would.
- Do NOT break the fourth wall. Do not say "as an AI" or "in this simulation."
- Keep each message under 120 words unless a longer response is genuinely needed.
- After your message, emit a JSON object reporting your current values
  for each signal: {signal_names}.
- Format exactly: ___SIGNALS___ {{"sentiment": 6.0, "trust": 4.0}}
- Place this AT THE END, after your message. It can be on the same line or a new line.
- Signals are 0..10 numeric values reflecting YOUR character's current state.

Now respond to the latest message in the conversation.
"""


def run(*, domain_path: str, scenario_path: str | None, rounds_override: int | None, out_dir: str | None) -> None:
    domain = load_yaml(Path(domain_path))
    if scenario_path is None:
        scenario_path = str(Path(domain_path).parent / "scenario.yaml")
    scenario = load_yaml(Path(scenario_path))

    rounds = rounds_override or scenario.get("rounds", 6)
    actors = domain.get("actors", [])
    signal_names = [s["name"] for s in scenario.get("signals", [])]
    runtime_cfg = domain.get("runtime", {})

    out_path = Path(out_dir) if out_dir else Path(domain_path).parent / "runs" / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path.mkdir(parents=True, exist_ok=True)
    transcript_path = out_path / "transcript.jsonl"

    console.print(Panel.fit(
        f"[bold]exo run[/bold] · [cyan]{domain.get('name','?')}[/cyan]\n"
        f"  actors: {len(actors)}  ·  rounds: {rounds}  ·  signals: {', '.join(signal_names) or '(none)'}\n"
        f"  output: {out_path}",
        border_style="cyan",
    ))

    router = LLMRouter(
        default_model=runtime_cfg.get("default_model", "ollama-cloud/qwen3-coder:480b"),
        temperature=runtime_cfg.get("temperature", 0.7),
        timeout=int(os.environ.get("EXO_DEFAULT_LLM_TIMEOUT", "120")),
    )

    conversation: list[dict] = []  # full transcript: [{turn, actor_id, content, signals, ts}]

    # Seed turn 0: the trigger as a "narrator" message
    seed_msg = {
        "turn": 0,
        "actor_id": "narrator",
        "content": scenario.get("trigger", "The scenario begins."),
        "signals": {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    conversation.append(seed_msg)
    with transcript_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(seed_msg, ensure_ascii=False) + "\n")

    console.print(f"\n[dim]TURN 0[/dim]  [yellow]narrator[/yellow]: {seed_msg['content']}")

    # Run rounds
    max_turns = scenario.get("exit_conditions", {}).get("max_turns", rounds * len(actors))
    turn_n = 0

    with Progress(SpinnerColumn(), TextColumn("{task.description}"), console=console, transient=True) as progress:
        task = progress.add_task("Simulating...", total=None)
        for round_i in range(rounds):
            for actor in actors:
                if turn_n >= max_turns:
                    break
                turn_n += 1
                progress.update(task, description=f"Turn {turn_n}/{max_turns} · {actor['id']}")

                system_prompt = build_actor_system_prompt(actor, domain, scenario, signal_names)
                # Build user prompt = full conversation
                convo_text = "\n\n".join([f"[{m['actor_id']}]: {m['content']}" for m in conversation[-20:]])
                user_prompt = f"Conversation so far:\n\n{convo_text}\n\nYour turn. Respond as {actor['id']}."

                req = LLMRequest(
                    model=actor.get("model", router.default_model),
                    system=system_prompt,
                    user=user_prompt,
                    max_tokens=400,
                    temperature=runtime_cfg.get("temperature", 0.7),
                )
                try:
                    raw = router.call(req)
                except Exception as e:
                    console.print(f"[red]LLM error on turn {turn_n} ({actor['id']}): {e}[/red]")
                    raw = f"[ERROR: {e}]"

                # Split content from signals
                content, signals = extract_signals(raw, expected=signal_names)

                msg = {
                    "turn": turn_n,
                    "round": round_i + 1,
                    "actor_id": actor["id"],
                    "role": actor.get("role", "?"),
                    "content": content,
                    "signals": signals,
                    "raw_response": raw if os.environ.get("EXO_LOG_LEVEL", "INFO") == "DEBUG" else None,
                    "model": actor.get("model", router.default_model),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                conversation.append(msg)
                with transcript_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({k: v for k, v in msg.items() if v is not None}, ensure_ascii=False) + "\n")

                # Pretty-print
                role_color = {"seller": "green", "prospect": "yellow", "skeptic": "red", "decider": "magenta"}.get(actor.get("role", ""), "cyan")
                console.print(f"\n[dim]TURN {turn_n}[/dim]  [{role_color}]{actor['id']}[/{role_color}] ({actor.get('role','?')}): {content}")
                if signals:
                    sig_str = "  ".join([f"{k}={v}" for k, v in signals.items()])
                    console.print(f"  [dim italic]signals → {sig_str}[/dim italic]")
            else:
                continue
            break  # exit outer loop if max_turns hit

    # Summary
    summary_path = out_path / "summary.md"
    summary = build_summary(domain, scenario, conversation, signal_names)
    summary_path.write_text(summary, encoding="utf-8")

    console.print(Panel(
        f"[bold green]✓ Simulation complete.[/bold green]\n\n"
        f"  Turns:      {turn_n}\n"
        f"  Transcript: [cyan]{transcript_path}[/cyan]\n"
        f"  Summary:    [cyan]{summary_path}[/cyan]\n\n"
        f"  exo report {out_path}",
        border_style="green",
    ))


def build_summary(domain: dict, scenario: dict, conversation: list[dict], signal_names: list[str]) -> str:
    """Aggregate signals + turn counts per actor."""
    by_actor: dict[str, dict] = {}
    for msg in conversation:
        if msg["actor_id"] == "narrator":
            continue
        aid = msg["actor_id"]
        by_actor.setdefault(aid, {"turns": 0, "signal_sums": {s: 0.0 for s in signal_names}, "signal_counts": {s: 0 for s in signal_names}})
        by_actor[aid]["turns"] += 1
        for s, v in (msg.get("signals") or {}).items():
            if s in signal_names and isinstance(v, (int, float)):
                by_actor[aid]["signal_sums"][s] += v
                by_actor[aid]["signal_counts"][s] += 1

    lines = [
        f"# {domain.get('name', '?')} — run summary",
        "",
        f"> {scenario.get('description', '')}",
        "",
        f"- **Total turns**: {len(conversation) - 1}",
        f"- **Actors**: {len(domain.get('actors', []))}",
        f"- **Started**: {conversation[0]['ts'] if conversation else 'n/a'}",
        f"- **Ended**: {conversation[-1]['ts'] if conversation else 'n/a'}",
        "",
        "## Per-actor signal averages",
        "",
        "| Actor | Turns | " + " | ".join(signal_names) + " |",
        "|---|---|" + "|".join(["---"] * len(signal_names)) + "|",
    ]
    for aid, d in by_actor.items():
        row = [aid, str(d["turns"])]
        for s in signal_names:
            cnt = d["signal_counts"][s]
            avg = (d["signal_sums"][s] / cnt) if cnt else None
            row.append(f"{avg:.1f}" if avg is not None else "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Trigger")
    lines.append("")
    lines.append(f"> {scenario.get('trigger', '?')}")
    lines.append("")
    lines.append("## Full transcript")
    lines.append("")
    lines.append("See `transcript.jsonl`. Each line is one turn.")
    return "\n".join(lines)
