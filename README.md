<div align="center">

# exo

**Multi-agent simulation engines for any domain.**
**Designed in 12 questions. Running in 30 minutes. Yours forever.**

[![Docker](https://img.shields.io/badge/Docker-compose%20up-2496ED?style=flat-square&logo=docker&logoColor=white)](#quickstart)
[![License: AGPL-3.0](https://img.shields.io/badge/License-AGPL--3.0-blue?style=flat-square)](./LICENSE)
[![Status: experimental](https://img.shields.io/badge/status-experimental-orange?style=flat-square)]()

</div>

---

> **What if you could simulate the next quarter of your sales pipeline before working on it?**
> **The likely reactions to a press release before publishing it?**
> **A construction site's stakeholder dynamics before a contract dispute lands?**
>
> The infrastructure for these simulations exists ([CAMEL-AI](https://github.com/camel-ai/camel), [OASIS](https://github.com/camel-ai/oasis), [MiroFish](https://github.com/nikmcfly/MiroFish-Offline)). What doesn't exist is the **opinionated bundle that lets you stand one up for your domain in an afternoon, without renting it from a vendor.**
>
> That's `exo`.

## What it is

`exo` is an opinionated starter kit for multi-agent simulation engines. It bundles:

- **Memory architecture** — Qdrant (vector) + Neo4j (graph) + Postgres (structured). The canonical hybrid stack from the [2026 agent-memory guide](./docs/memory-architecture.md). **All three are optional and lazy-started** — a simple 4-actor chat sim runs with zero databases. The DBs only spin up when your `domain.yaml` declares a memory tier that needs them.
- **LLM router** — Routes requests between Claude OAuth (frontier), Ollama Cloud (cloud OSS), and local Ollama / BERTHA / llama-swap (local OSS). No API keys baked in.
- **Multi-agent runtime** — Built on [CAMEL-AI](https://github.com/camel-ai/camel) and [OASIS](https://github.com/camel-ai/oasis). Same engine that powers Mirofish.
- **`exo architect`** — Interactive CLI that walks you through the 12 design decisions for a new multi-agent simulation: actors, ontology, scenarios, memory tier, LLM tier. Outputs a complete `domain.yaml` + ready-to-run docker setup.
- **Template library** — Pre-built simulations for common domains: social-media reaction, sales pipeline, wedding-vendor coordination, healthcare triage, construction stakeholder, software incident response.
- **YAML-first config** — Every aspect of a simulation (actors, personas, scenarios, memory routing, output schemas) is declared in one file. No hidden Python. Version it. Diff it. Share it.

## Why does this exist?

If you spend any time on AI Twitter / dev YouTube / homelab Reddit, you've probably seen variations of: "I want to build a personal AI that lets me <X>." The advice is usually:

1. "Use LangChain" → too generic, gets thrown away.
2. "Use LangGraph" → real, but assumes you've already designed the architecture.
3. "Use n8n" → wires services; doesn't build memory.
4. "Use CrewAI" → multi-agent, but no opinion on the memory tier.
5. "Build from scratch" → fine if you're a senior infra engineer with three months.

**There's no "I want a multi-agent simulation for my domain, here's a docker-compose, what should I edit" answer.** Everything is either too generic to ship or too custom to copy.

`exo` is opinionated about three things and unopinionated about everything else:

1. **The memory tiers are catalogued, not mandatory.** Vector + Graph + Structured are available. You pick which your sim needs in YAML. Small sims run with zero databases. Memory is pay-as-you-go, not baked in.
2. **The configuration is YAML.** Not Python, not JSON, not a web UI. Edit one file; run.
3. **The bundle is local-first.** It runs on a laptop. It runs on a homelab. It runs against Ollama Cloud or against your local llama-swap. It does not require an OpenAI key. If you want frontier intelligence, plug Claude OAuth or Ollama Cloud; if you don't, run qwen2.5 locally and accept the quality tradeoff.

## What's the actual contribution?

Honest answer: exo doesn't invent multi-agent simulation. CAMEL-AI and OASIS already do that excellently. The contribution is **the deterministic architect step plus the YAML-first config plus the actor-model decoupling that lets every actor run on a different LLM tier without code changes.**

Put more concretely:

- Existing tools require you to design the simulation in code. exo lets you design it in 12 questions through a CLI that emits a versionable YAML spec. The recommendation engine is rule-based — no LLM-in-the-loop deciding your architecture, which means deterministic, reproducible, and testable design decisions.
- Existing tools assume one LLM per simulation. exo's `actor.model` field is per-actor: you can have a senior-VP actor running Claude OAuth (frontier intelligence for the decision-maker) while three skeptical-employee actors run qwen2.5 locally (cheap, fast, slightly less coherent — which is also more realistic for the role).
- Existing tools bundle the multi-agent runtime with a specific memory backend choice. exo's memory tier is declared in YAML and only the layers your sim needs get instantiated.

That decoupling is the value-add. It's not novel research; it's an opinionated assembly that closes the gap between "I want a sim of X" and "I have a transcript of X."

## Quickstart

```bash
# 1. Clone + start the stack
git clone https://github.com/<your-org>/exo.git
cd exo
docker compose up -d

# 2. Pick an example, or design a new one
exo architect              # 12-question walkthrough → ./my-sim/domain.yaml
# OR
cp -r templates/sales-pipeline my-sim
cd my-sim

# 3. Run a simulation
exo run --config domain.yaml --scenario my-scenario.yaml

# 4. Inspect outputs
open http://localhost:5050/        # web UI: actor inspector + graph + transcripts
exo report --run latest            # text report
```

That's the whole experience. Five commands. One YAML file to edit.

## The architect (the value-add)

The `exo architect` CLI is the part you'll actually use the most. It's twelve questions:

```
$ exo architect
What's the working name for this simulation? [my-sim]
> sales-rehearsal

In one sentence, what does this simulation answer for you?
> What's the most likely failure mode when I pitch to Joseph Armanios next week?

What kind of system are you simulating?
  1. Social platform (Reddit/Twitter-style reactions)
  2. Organizational stakeholders (boardroom, project team)
  3. Market dynamics (pricing, supply/demand)
  4. Customer service / sales interaction
  5. Custom — describe it
> 4

How many actors?
  small (3-8)   medium (10-30)   large (50-200)
> small

[...10 more questions...]

Writing my-sim/domain.yaml...
Writing my-sim/scenario.yaml...
Writing my-sim/compose.override.yaml (LLM = ollama-cloud, embedding = local-bertha)...

✓ Ready. Run: cd my-sim && exo run
```

Output is a `domain.yaml` like this — committable, diffable, shareable:

```yaml
# my-sim/domain.yaml
name: sales-rehearsal
purpose: Identify failure modes for the Armanios pitch
memory:
  tier: vector+graph     # exo chose this from your answers
  vector_backend: qdrant
  graph_backend: neo4j
actors:
  - id: michael
    persona: Founder, technical, prone to over-explaining
    role: seller
    model: claude-oauth
  - id: armanios
    persona: Construction-domain SVP, allergic to vendor speak, hot under deadline
    role: prospect
    model: ollama-cloud/qwen3-coder:480b
  - id: gerges
    persona: Co-decision-maker, watches for tech debt
    role: prospect
    model: ollama-cloud/qwen3-coder:480b
scenario:
  trigger: Michael opens the pitch with a 5-minute walkthrough demo
  duration: 30 minutes
  signals:
    - prospect emotional valence (1-10)
    - prospect questions about pricing
    - prospect commitments to next step
```

You commit that file. You run `exo run`. You get a transcript. You compare against reality next week.

## Examples included

| Template | What it simulates | Time to first run |
|---|---|---|
| `social-media-reaction` | Public reaction to a press release / policy doc (Mirofish-style) | ~5 min |
| `sales-pipeline` | Multi-stakeholder sales conversation, deal progression | ~3 min |
| `wedding-vendor-coordination` | Vendor + couple + venue logistics over a planning timeline | ~5 min |
| `healthcare-triage` | ER intake → diagnostic agents → treatment recommendation | ~8 min |
| `construction-stakeholder` | PM/Estimator/Foreman/Exec/Subcontractor on a project conflict | ~5 min |
| `incident-response` | On-call engineers + product + manager during a P0 | ~5 min |

Each one is a directory you `cp -r` and edit. Each one runs against the same stack.

## What this is NOT

- **Not a LangChain replacement.** LangChain wraps API calls; exo runs full simulations with persistent memory.
- **Not a chatbot framework.** This is for *simulating populations of agents*, not building one conversational assistant.
- **Not production-grade.** v0.1. Treat it like a research toy that happens to be docker-compose-ready.
- **Not opinionated about deploy.** If you want Kubernetes, fork it. If you want a SaaS version, you're holding the wrong thing.

## What's under the hood

`exo` is shamelessly built on the giants. The opinionated bundle is the value; the libraries underneath are battle-tested:

- [CAMEL-AI](https://github.com/camel-ai/camel) — the agent runtime
- [OASIS](https://github.com/camel-ai/oasis) — multi-agent social simulation
- [Neo4j](https://neo4j.com/) — graph DB
- [Qdrant](https://qdrant.tech/) — vector DB
- [LightRAG](https://github.com/HKUDS/LightRAG) — graph + vector RAG layer (used optionally)
- [PostgreSQL](https://www.postgresql.org/) — structured records
- [Ollama](https://ollama.com/) — local LLM runtime
- [Ollama Cloud](https://ollama.com/cloud) — frontier OSS models via API
- [Claude OAuth](https://www.anthropic.com/) — frontier inference via Claude Code

If you've used [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline), exo is the generalization of its architecture: same engine, vendor-neutral, YAML-first, designed for any domain.

## License

AGPL-3.0. Build on it. If you ship a SaaS, share the SaaS code.

## Status

v0.1.0. Experimental. The architecture is locked; the templates are real but minimal. Issues and PRs welcome.

---

<div align="center">
<sub>Built because the gap between "I want to simulate X" and "I have a running multi-agent simulation of X" should be one YAML file, not three months.</sub>
</div>
