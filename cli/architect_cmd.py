"""exo architect — 12-question interactive walkthrough.

Output: <name>/domain.yaml + <name>/scenario.yaml.

Deterministic rule-based recommendation engine — no LLM in the design path.
The architect is the design step; LLMs come in at simulation time.
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt, Confirm

console = Console()


SYSTEM_KINDS = [
    ("social-platform", "Social platform (Reddit/Twitter-style reactions, public-opinion modeling)"),
    ("organizational", "Organizational stakeholders (boardroom, project team, contract dispute)"),
    ("market", "Market dynamics (pricing, supply/demand, negotiation)"),
    ("customer-service", "Customer service / sales interaction"),
    ("healthcare", "Healthcare triage / clinical reasoning"),
    ("incident-response", "Incident response (on-call, escalation, resolution)"),
    ("custom", "Custom — I'll describe it"),
]

ACTOR_SCALES = [
    ("small", "small (3-8 actors)"),
    ("medium", "medium (10-30 actors)"),
    ("large", "large (50-200 actors)"),
]

MEMORY_NEEDS = [
    ("conversation", "Just conversation history — actors remember what was said"),
    ("relational", "Conversation + relationships between actors (who-knows-whom, who-trusts-whom)"),
    ("knowledge", "Conversation + a shared knowledge corpus actors can retrieve from"),
    ("everything", "Conversation + relationships + knowledge corpus + structured records"),
]

LLM_PREFERENCE = [
    ("claude-oauth", "Claude OAuth (frontier intelligence; uses your Claude Code login)"),
    ("ollama-cloud", "Ollama Cloud (cloud OSS frontier; nemotron/qwen3-coder/deepseek/kimi)"),
    ("local-ollama", "Local Ollama / llama-swap (zero cost, smaller models)"),
    ("mixed", "Mixed: frontier for hard actors, local for simple ones"),
]


def slugify(s: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", s.strip().lower())
    return re.sub(r"-+", "-", s).strip("-")


def ask_choice(prompt: str, choices: list[tuple[str, str]], default_idx: int = 0, non_interactive: bool = False) -> str:
    if non_interactive:
        return choices[default_idx][0]
    console.print(f"\n[bold cyan]{prompt}[/bold cyan]")
    for i, (_, desc) in enumerate(choices, 1):
        marker = " (default)" if i - 1 == default_idx else ""
        console.print(f"  {i}. {desc}{marker}")
    while True:
        raw = Prompt.ask("Choose", default=str(default_idx + 1))
        try:
            idx = int(raw)
            if 1 <= idx <= len(choices):
                return choices[idx - 1][0]
        except ValueError:
            pass
        console.print("[red]Please enter a number from the list.[/red]")


def recommend_memory_tier(memory_need: str) -> dict:
    if memory_need == "conversation":
        return {"tier": "none", "vector_backend": "none", "graph_backend": "none", "sql_backend": "none"}
    if memory_need == "relational":
        return {"tier": "graph", "vector_backend": "none", "graph_backend": "neo4j", "sql_backend": "none"}
    if memory_need == "knowledge":
        return {"tier": "vector", "vector_backend": "qdrant", "graph_backend": "none", "sql_backend": "none"}
    return {"tier": "vector+graph+sql", "vector_backend": "qdrant", "graph_backend": "neo4j", "sql_backend": "postgres"}


def recommend_default_model(llm_pref: str) -> str:
    return {
        "claude-oauth": "claude-oauth",
        "ollama-cloud": "ollama-cloud/qwen3-coder:480b",
        "local-ollama": "local-ollama/qwen2.5:14b",
        "mixed": "ollama-cloud/qwen3-coder:480b",
    }[llm_pref]


def stub_actors(scale: str, default_model: str, system_kind: str) -> list[dict]:
    """Generate a starter set of actors based on the system kind.
    User can edit. This is just a sane default."""
    presets = {
        "social-platform": [
            ("agent_a", "Influencer with 50k followers, opinion-leader on this topic", "influencer"),
            ("agent_b", "Skeptical journalist, looks for inconsistencies", "skeptic"),
            ("agent_c", "Casual reader, picks side based on first viral take", "follower"),
            ("agent_d", "Affected stakeholder, has direct experience in this domain", "stakeholder"),
        ],
        "organizational": [
            ("project_manager", "Practical, deadline-driven, owns delivery", "owner"),
            ("estimator", "Numbers-first, allergic to handshake commitments", "analyst"),
            ("foreman", "Field-experienced, prioritizes worker safety + practicality", "operator"),
            ("executive", "Strategic, watches the P&L, intolerant of detail", "decider"),
            ("skeptic", "Internal critic who has seen this play out before", "skeptic"),
        ],
        "market": [
            ("buyer_a", "Cost-sensitive, comparison-shops, will walk", "buyer"),
            ("buyer_b", "Loyalty-driven, returns to known brands", "buyer"),
            ("seller", "Pricing the product, watching demand", "seller"),
            ("competitor", "Mirrors the seller's moves with a lag", "rival"),
        ],
        "customer-service": [
            ("customer", "Frustrated, deadline-pressured, has prior negative experiences", "customer"),
            ("agent", "Service-oriented, follows scripts, has authority for $X concessions", "agent"),
            ("supervisor", "Escalation target, watches metrics, defends company position", "manager"),
        ],
        "healthcare": [
            ("patient", "Symptomatic, anxious, partial-information self-report", "patient"),
            ("triage_nurse", "Risk-stratifies, prioritizes by acuity, time-pressured", "intake"),
            ("attending", "Diagnostic reasoning, owns the treatment plan", "decider"),
            ("specialist", "Consulted on uncertainty, focused on differential dx", "consultant"),
        ],
        "incident-response": [
            ("on_call_eng", "Tired, mid-incident, owns the fix", "owner"),
            ("incident_commander", "Coordinates, runs the channel, watches the clock", "coordinator"),
            ("product_manager", "Pressures for ETA, customer-facing comms", "stakeholder"),
            ("manager", "Decides escalation, calls in reinforcements", "decider"),
        ],
        "custom": [
            ("actor_a", "First actor — replace with your real persona", "primary"),
            ("actor_b", "Second actor — replace with your real persona", "secondary"),
            ("actor_c", "Third actor — replace with your real persona", "tertiary"),
        ],
    }
    presets_for_kind = presets.get(system_kind, presets["custom"])
    if scale == "small":
        presets_for_kind = presets_for_kind[: min(4, len(presets_for_kind))]
    elif scale == "medium":
        # Duplicate with variation for medium-size sims
        base = presets_for_kind
        out = []
        for i, (aid, p, r) in enumerate(base * 3):
            out.append((f"{aid}_{i+1}", p, r))
            if len(out) >= 12:
                break
        return [{"id": aid, "persona": p, "role": r, "model": default_model} for aid, p, r in out]
    # large: stub a few, document that user expands
    return [{"id": aid, "persona": p, "role": r, "model": default_model} for aid, p, r in presets_for_kind]


def run(*, name: str | None, out_dir: str | None, non_interactive: bool) -> None:
    console.print(Panel.fit(
        "[bold]exo architect[/bold] — design a multi-agent simulation tailored to YOUR machine.\n"
        "Step 1: scan your hardware + services + accounts.\n"
        "Step 2: 12 questions about the simulation.\n"
        "Output: a [cyan]domain.yaml[/cyan] that uses what you actually have, not generic defaults.",
        border_style="cyan",
    ))

    # === Step 1: Hardware-aware preflight ===
    from exo_runtime.doctor import run_doctor, recommend_from_doctor

    extra_hosts: list[str] = []
    user_cloud_accounts: list[str] = []

    if not non_interactive:
        console.print("\n[bold cyan]Step 1.[/bold cyan] Scanning your machine for hardware + services...")
        # Initial probe of localhost only
        initial = run_doctor(extra_hosts=None)
        for line in initial.summary_lines:
            console.print(f"  {line}")

        # Ask about other devices
        other = Prompt.ask(
            "\n[bold cyan]Q-pre-1.[/bold cyan] Any other machines I should probe? (homelab IP, NAS, Proxmox node — comma-separated, or blank)",
            default="",
        )
        extra_hosts = [h.strip() for h in other.split(",") if h.strip()]

        if extra_hosts:
            console.print(f"\nProbing {extra_hosts}...")
            full = run_doctor(extra_hosts=extra_hosts)
            for line in full.summary_lines[len(initial.summary_lines):]:
                console.print(f"  {line}")
        else:
            full = initial

        # Ask about cloud accounts not in env vars
        more_cloud = Prompt.ask(
            "\n[bold cyan]Q-pre-2.[/bold cyan] Any cloud accounts not in env vars? (e.g., 'Vercel team', 'Modal', 'Fly.io' — comma-separated, or blank)",
            default="",
        )
        user_cloud_accounts = [c.strip() for c in more_cloud.split(",") if c.strip()]

        doctor_report = full
    else:
        # Non-interactive: scan localhost only, no probing prompts
        doctor_report = run_doctor(extra_hosts=None)

    doctor_recs = recommend_from_doctor(doctor_report)

    # === Q1: Name ===
    if not name:
        if non_interactive:
            name = "my-sim"
        else:
            name = Prompt.ask("\n[bold cyan]Q1.[/bold cyan] Working name for this simulation [kebab-case]", default="my-sim")
    name = slugify(name)

    # === Q2: Purpose ===
    purpose = Prompt.ask("\n[bold cyan]Q2.[/bold cyan] In one sentence, what does this simulation answer for you?",
                         default="Stress-test how stakeholders will react to a specific scenario") if not non_interactive else "Test sim"

    # === Q3: System kind ===
    system_kind = ask_choice("Q3. What kind of system are you simulating?", SYSTEM_KINDS, default_idx=1, non_interactive=non_interactive)

    custom_kind_desc = None
    if system_kind == "custom" and not non_interactive:
        custom_kind_desc = Prompt.ask("Describe the kind of system in 1 sentence", default="custom domain")

    # === Q4: Scale ===
    scale = ask_choice("Q4. How many actors?", ACTOR_SCALES, default_idx=0, non_interactive=non_interactive)

    # === Q5: Memory need ===
    memory_need = ask_choice("Q5. What memory does the simulation need?", MEMORY_NEEDS, default_idx=0, non_interactive=non_interactive)

    # === Q6: LLM preference ===
    llm_pref = ask_choice("Q6. Where should LLM inference go?", LLM_PREFERENCE, default_idx=1, non_interactive=non_interactive)

    # === Q7: Turn count ===
    if non_interactive:
        rounds = 6
    else:
        rounds = IntPrompt.ask("\n[bold cyan]Q7.[/bold cyan] How many turns per actor (a single round = each actor speaks once)?", default=6)

    # === Q8: Scenario trigger ===
    if non_interactive:
        trigger = "An external event forces the actors into discussion."
    else:
        trigger = Prompt.ask("\n[bold cyan]Q8.[/bold cyan] What's the trigger event that starts the simulation?",
                             default="An external event forces the actors into discussion.")

    # === Q9: Determinism need ===
    if non_interactive:
        temperature = 0.7
    else:
        temp_choice = Prompt.ask("\n[bold cyan]Q9.[/bold cyan] How deterministic should the simulation be? (0=very deterministic, 1=creative/varied)",
                                 default="0.7")
        try:
            temperature = float(temp_choice)
        except ValueError:
            temperature = 0.7

    # === Q10: Signals to track ===
    if non_interactive:
        signals = ["sentiment", "trust"]
    else:
        signals_raw = Prompt.ask("\n[bold cyan]Q10.[/bold cyan] What signals should the runner track per turn? (comma-separated)",
                                 default="sentiment,trust,commitment")
        signals = [s.strip() for s in signals_raw.split(",") if s.strip()]

    # === Q11: Exit condition ===
    if non_interactive:
        exit_after = rounds
    else:
        exit_after = IntPrompt.ask("\n[bold cyan]Q11.[/bold cyan] Stop after how many total turns?", default=rounds * 2)

    # === Q12: Output format ===
    if non_interactive:
        output_format = "jsonl"
    else:
        output_format = Prompt.ask("\n[bold cyan]Q12.[/bold cyan] Transcript format", choices=["jsonl", "yaml", "both"], default="jsonl")

    # === Build domain.yaml — using doctor recommendations to pick concrete backends ===
    memory_spec = recommend_memory_tier(memory_need)
    # Override generic memory backend hints with what we actually detected
    if memory_spec["tier"] != "none":
        if "vector" in memory_spec["tier"] and doctor_recs.get("vector_store"):
            memory_spec["vector_backend"] = doctor_recs["vector_store"]
        if "graph" in memory_spec["tier"] and doctor_recs.get("graph_store"):
            memory_spec["graph_backend"] = doctor_recs["graph_store"]
        if "sql" in memory_spec["tier"] and doctor_recs.get("sql_store"):
            memory_spec["sql_backend"] = doctor_recs["sql_store"]

    # Pick the actor default model from the doctor's recommendation, NOT the generic question.
    # The user's question 6 (LLM preference) is now a HINT, not the authoritative choice —
    # doctor sees what's actually available.
    default_model = doctor_recs.get("primary_llm") or recommend_default_model(llm_pref)
    fallback_model = doctor_recs.get("fallback_llm")
    actors = stub_actors(scale, default_model, system_kind)

    domain = {
        "name": name,
        "purpose": purpose,
        "created": datetime.now(timezone.utc).isoformat(),
        "created_by": "exo-architect v0.1.0 (hardware-aware)",
        "system_kind": system_kind,
        "custom_kind_description": custom_kind_desc,
        "scale": scale,
        "memory": memory_spec,
        "actors": actors,
        "runtime": {
            "default_model": default_model,
            "fallback_model": fallback_model,
            "llm_preference": llm_pref,
            "temperature": temperature,
            "parallel_agents": min(4, len(actors)),
            "log_level": "INFO",
        },
        "machine_profile": {
            # Persist a snapshot of WHY these picks were made — auditable later
            "scanned_at": doctor_report.timestamp,
            "os": f"{doctor_report.hardware.os} {doctor_report.hardware.os_release}",
            "ram_gb": doctor_report.hardware.ram_total_gb,
            "gpu": doctor_report.hardware.gpu_name,
            "extra_hosts_probed": extra_hosts,
            "extra_cloud_accounts": user_cloud_accounts,
            "doctor_notes": doctor_recs.get("notes", []),
        },
    }

    scenario = {
        "name": f"{name}-default",
        "domain_ref": "./domain.yaml",
        "description": purpose,
        "trigger": trigger,
        "initial_context": (
            f"This is a simulation of: {purpose}. The actors are: "
            + ", ".join([f"{a['id']} ({a['role']})" for a in actors])
            + f". The triggering event is: {trigger}"
        ),
        "rounds": rounds,
        "exit_conditions": {"max_turns": exit_after, "max_minutes": 30},
        "signals": [
            {"name": s, "type": "numeric", "scale": "0..10", "description": f"Track {s} per actor per turn."}
            for s in signals
        ],
        "output": {"format": output_format, "directory": "./runs/"},
    }

    out_path = Path(out_dir) if out_dir else Path.cwd() / name
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "domain.yaml").write_text(yaml.safe_dump(domain, sort_keys=False, allow_unicode=True), encoding="utf-8")
    (out_path / "scenario.yaml").write_text(yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True), encoding="utf-8")

    # Write a README for the sim
    readme = f"""# {name}

> {purpose}

Designed with `exo architect` on {datetime.now(timezone.utc).date().isoformat()}.

## Run

```bash
exo run domain.yaml
```

## Edit

- **`domain.yaml`** — actors, memory tier, runtime config. Edit personas to taste; add or remove actors freely.
- **`scenario.yaml`** — the trigger event, signals to track, turn count. Run multiple scenarios against the same domain.

## What got recommended

- Memory tier: **{memory_spec['tier']}** ({memory_need})
- Default model: **{default_model}** ({llm_pref})
- Actor scale: {scale} ({len(actors)} actors)

Tune in `domain.yaml`.
"""
    (out_path / "README.md").write_text(readme, encoding="utf-8")

    console.print(Panel(
        f"[bold green]✓ Designed.[/bold green]\n\n"
        f"  [cyan]{out_path / 'domain.yaml'}[/cyan]   ({len(actors)} actors, memory={memory_spec['tier']})\n"
        f"  [cyan]{out_path / 'scenario.yaml'}[/cyan]\n"
        f"  [cyan]{out_path / 'README.md'}[/cyan]\n\n"
        f"Run with:\n  [bold]cd {out_path.name} && exo run domain.yaml[/bold]",
        border_style="green",
    ))
