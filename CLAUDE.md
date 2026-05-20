# exo — agent instructions

## Project context

exo is a CLI for diagnosing, planning, and executing on infrastructure you own. Currently shipped:
- `exo doctor` — local hardware + service probe
- `exo solve` — read a data source, identify issues, propose action plan
- `exo recommend` — score candidate repos against live GitHub signals (no LLM bias)
- `exo execute` — walk a solve plan with safety-classified consent gates
- `exo plan` — fleet rebalancing (K8s scheduler + DRS + 7 Rs framework grounding)
- `exo memory` — persistent session store at ~/.exo/sessions.db
- Public leaderboard at https://mgbuilds9.github.io/exo/

All algorithm choices map to published frameworks in `docs/PRINCIPLES.md`.

## Conventions

- Python 3.11+, click for CLI wiring, rich for terminal UI, pyyaml for configs
- Tests live in `tests/`, run via `python -m pytest tests/ -q`
- Subcommands: `cli/<name>_cmd.py` for entry, `exo_runtime/<name>/` for logic
- Every new capability needs an entry in `docs/PRINCIPLES.md` citing its framework basis

## Design System

Always read `DESIGN.md` before making any visual or UI decisions. All font
choices, colors, spacing, layout grids, motion timings, and aesthetic
direction are defined there. Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match `DESIGN.md`.

Two views are first-class: `Topology` (default, daily-driver, light ops-room)
and `Pulse` (secondary, organic glance, dark default). Both inherit shared
semantic color tokens and the Atkinson Hyperlegible + Recursive Mono +
PT Serif type system.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke context-save / context-restore
- Code quality, health check → invoke health
