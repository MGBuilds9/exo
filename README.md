<div align="center">

# exo

**A 600-line Python wrapper that runs multi-actor LLM conversations from a YAML file.**
**With a deterministic CLI that scans your machine and picks concrete LLM/storage backends from what you actually have.**

*v0.1 — designed for 3–12 actor rehearsal sims. Plausible role-play with measurable variance, not calibrated predictions.*

[![Docker](https://img.shields.io/badge/Docker-compose%20up-2496ED?style=flat-square&logo=docker&logoColor=white)](#quickstart)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache--2.0-blue?style=flat-square)](./LICENSE)
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

- **Memory architecture** — Qdrant (vector) + Neo4j (graph) + Postgres (structured) defined in `compose.yaml` as profile-gated services. **You opt them in manually**: `docker compose --profile graph up` will start Neo4j alongside the runner. There is no auto-detection from `domain.yaml`; if you declare a memory tier, you also pass the matching profile flag at start time. (v0.2 may automate this; v0.1 is manual.)
- **LLM router** — Routes requests between Claude OAuth (frontier), Ollama Cloud (cloud OSS), and local Ollama / BERTHA / llama-swap (local OSS). Pick one of these in your environment — you supply the credentials (`OLLAMA_API_KEY`, Claude Code OAuth login, or a local Ollama at `LOCAL_OLLAMA_BASE_URL`). exo does not ship any keys; you choose which provider you trust.
- **Multi-agent runtime** — A vendor-neutral turn-loop in pure Python (~600 lines). Each turn, each actor speaks once via its configured LLM; conversation state is the shared context. Not built on CAMEL-AI or OASIS in v0.1, though the design is informed by what those projects do well. v0.2 will add CAMEL-AI integration as an opt-in runtime.
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

## Architecture (one diagram)

```
                  ┌──────────────────────────┐
                  │      exo architect       │  ◄── 12-question walkthrough
                  │  (deterministic CLI)     │      writes domain.yaml + scenario.yaml
                  └────────────┬─────────────┘
                               │
                       domain.yaml + scenario.yaml
                               │
                               ▼
              ┌────────────────────────────────────┐
              │            exo run                 │
              │   ┌─────────────────────────┐      │
              │   │   Multi-actor loop      │      │
              │   │ For each round, each    │      │
              │   │ actor speaks in turn    │      │
              │   └──────────┬──────────────┘      │
              │              │                     │
              │              ▼                     │
              │   ┌─────────────────────────┐      │
              │   │  LLM Router (per actor) │      │
              │   └──┬───────────┬───────┬──┘      │
              │      │           │       │         │
              │      ▼           ▼       ▼         │
              │  Claude     Ollama   Local         │
              │  OAuth      Cloud    Ollama        │
              │              API     /BERTHA       │
              │                                    │
              │   ┌─────────────────────────┐      │
              │   │ Memory tiers (optional) │      │
              │   │ Qdrant │ Neo4j │ Postgres│      │
              │   │ vector │ graph │ structured│   │
              │   └─────────────────────────┘      │
              │                                    │
              └─────────────┬──────────────────────┘
                            │
                            ▼
                  transcript.jsonl + summary.md
                  + signal trajectories per actor
```

Three things to notice:
1. **The architect is deterministic** (rule-based, not LLM-in-the-loop). Same answers → same `domain.yaml`. Testable, diffable.
2. **Each actor picks its own LLM** in YAML. Frontier for the hard role, local for the cheap ones. No code changes.
3. **Memory tiers are optional** and only spin up when `domain.yaml` declares them. Simple chat sims don't load Qdrant/Neo4j/Postgres.

## What's the actual contribution?

Honest answer: exo doesn't invent multi-agent simulation. CAMEL-AI and OASIS already do that excellently. The contribution is **the deterministic architect step plus the YAML-first config plus the actor-model decoupling that lets every actor run on a different LLM tier without code changes.**

Put more concretely:

- Existing tools require you to design the simulation in code. exo lets you design it in 12 questions through a CLI that emits a versionable YAML spec. The recommendation engine is rule-based — no LLM-in-the-loop deciding your architecture, which means deterministic, reproducible, and testable design decisions.
- Existing tools assume one LLM per simulation. exo's `actor.model` field is per-actor: you can have a senior-VP actor running Claude OAuth (frontier intelligence for the decision-maker) while three skeptical-employee actors run qwen2.5 locally (cheap, fast, slightly less coherent — which is also more realistic for the role).
- Existing tools bundle the multi-agent runtime with a specific memory backend choice. exo's memory tier is declared in YAML and only the layers your sim needs get instantiated.

That decoupling is the value-add. It's not novel research; it's an opinionated assembly that closes the gap between "I want a sim of X" and "I have a transcript of X."

## Under 5 minutes from clone to first transcript (no Docker, no cloud)

For the impatient. Local Ollama only:

```bash
# 1. One-time setup (~3 min): Python 3.11+ and Ollama
ollama pull qwen2.5:7b      # ~4GB
ollama serve &

# 2. Clone + first transcript (~90 sec)
git clone https://github.com/MGBuilds9/exo.git
cd exo
pip install -r requirements.txt   # 4 deps: click pyyaml rich requests
sed -i 's|ollama-cloud/qwen3-coder:480b|local-ollama/qwen2.5:7b|g' \
    templates/sales-pipeline/domain.yaml
export LOCAL_OLLAMA_BASE_URL=http://localhost:11434/v1
./exo run templates/sales-pipeline/domain.yaml --rounds 2
```

8 turns of real B2B sales rehearsal printed live with signals tracked
per actor. Zero data leaves your machine. Total wallclock: ~5 minutes
clone-to-transcript if you already have Python + Ollama installed.

Want frontier-model output instead of local? Drop the `sed`, set
`OLLAMA_API_KEY` instead of `LOCAL_OLLAMA_BASE_URL`. Same command.

## Quickstart (full stack with memory tiers)

```bash
# 1. Clone + start the stack
git clone https://github.com/MGBuilds9/exo.git
cd exo
docker compose up -d            # runner only; DBs are opt-in via --profile

# 2. Pick an example, or design a new one
exo architect              # 12-question walkthrough → ./my-sim/domain.yaml
# OR
cp -r templates/sales-pipeline my-sim
cd my-sim

# 3. Run a simulation
exo run --config domain.yaml --scenario my-scenario.yaml

# 4. Inspect outputs
exo report sims/<your-sim>/run/    # text report
# (web UI at localhost:5050 is a v0.2 deliverable; v0.1 is CLI-only)
```

That's the whole experience. Five commands. One YAML file to edit.

## The actual differentiator: it knows YOUR machine

Every other multi-agent framework (CAMEL, OASIS, LangChain, CrewAI) assumes you'll wire your own LLM endpoint, your own vector store, your own embedding model. They give you a config to fill in. **exo asks what you have and builds the config for you.**

```bash
./exo doctor
```

Scans:
- CPU cores, RAM, GPU (filtered for real GPUs, not virtual display adapters)
- Disk space across all your drives
- Running services on `localhost`: Ollama, LM Studio, Qdrant, Neo4j, Postgres, SearXNG, Docker daemon
- Optional: any IP you give it (`--host 192.168.0.19`) — probes your homelab too
- CLIs in PATH: Claude Code, Ollama, Docker
- Cloud account env vars: `OLLAMA_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.

Then **recommends a personalized stack**:

```
Recommendations based on what you actually have
─────────────────────────────────────────────────
primary LLM:    claude-oauth                                  ← detected Claude Code CLI
fallback LLM:   ollama-cloud/qwen3-coder:480b                 ← detected OLLAMA_API_KEY
embedding:      ollama/bge-m3:latest                          ← already loaded locally
vector store:   chroma-embedded                               ← no Qdrant; zero-ops alternative
graph store:    neo4j-local                                   ← detected at localhost:7474
sql store:      sqlite-embedded                               ← no Postgres; fine for personal sims
hosting:        local-docker                                  ← Docker running
```

When you run `exo architect`, this report flows into the design. The `domain.yaml` it generates has `actor.model: claude-oauth` (because you have it) — not a generic placeholder you have to swap. A snapshot of WHY these picks were made is persisted in `domain.yaml`'s `machine_profile` section for audit.

This is what makes exo different from "another Docker compose with three vendor wrappers."

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

## What a run actually looks like

Real 20-turn output from `exo run templates/sales-pipeline/domain.yaml`,
using qwen3-coder:480b via Ollama Cloud (~140s, ~$0.02 in tokens):

```
TURN 1  founder (seller): Hi everyone, thanks for taking the time to meet again!
  I'm really excited to dive deeper into how our multi-agent simulation platform
  can help your estimating and project management teams prepare for complex
  stakeholder interactions...
  signals → prospect_interest=5.0  trust=4.0

TURN 2  vp_operations (prospect-decider): "Thanks for following up. Look, I'll
  be direct - I've seen three AI demos that sounded great but never delivered.
  My team's time is money, especially during bid season. You mentioned
  communication patterns - show me the workflow where this actually saves us
  time..."
  signals → prospect_interest=5.0  trust=3.0  deal_momentum=4.0

TURN 3  cfo (prospect-financial): "Before we dive into workflows, I'd like to
  understand the financial structure. What does licensing look like - per seat,
  per project, or annual subscription? I've done our internal build-vs-buy
  analysis already..."
  signals → prospect_interest=5.0  trust=4.0  deal_momentum=3.0

TURN 4  it_director (prospect-technical): "Before we move forward, I need
  specifics on technical architecture. You mentioned on-prem deployment - what
  about Docker compatibility? Kubernetes support? Air-gapped environments?"
  signals → prospect_interest=4.0  trust=4.0  deal_momentum=3.0

[... 16 more turns ...]
```

Full transcript: [`examples/sales-pipeline-rehearsal/`](./examples/sales-pipeline-rehearsal/) — 21 turns, 4 actors, ~140s real wallclock against Ollama Cloud qwen3-coder:480b. The repository ships THREE independent runs of the same template:

- `transcript.jsonl` — Run 1 (20 turns)
- `transcript-run-2.jsonl` — Run 2 (20 turns)
- `transcript-run-3.jsonl` — Run 3 (20 turns)

Each ~140 seconds. ~$0.02 in tokens per run. Reproducible: see the
"Reproducibility" section below for the exact commands.

Each prospect surfaces objections specific to their function. The
cross-run variance section above quantifies what's different between
runs.

## What this is and isn't

**Is:** a deterministic CLI (the architect + doctor) that picks concrete backends for your machine, plus a turn-loop runtime that drives multi-actor LLM conversations from YAML. Self-reported per-actor signals (sentiment / trust / etc.) come from the actors themselves at each turn — they're plausible role-play artifacts, not predictions calibrated against ground truth. Designed for 3–12 actor simulations; >20 actors per sim is untested.

**Isn't:** a production-grade multi-agent system, a calibrated prediction engine, or a replacement for OASIS/CAMEL-AI for social-media simulation specifically. The runtime is ~600 lines of Python — a turn-loop, an LLM router, a signal extractor. The value is the bundle + the architect, not the runtime sophistication.

## Cross-run variance — what the simulator does that a single prompt doesn't

The same template (`templates/sales-pipeline/`) run three times against
the same prospects produces three different conversations with measurable
behavioral variance. Per-actor `deal_momentum` deltas across 3 independent
runs:

| Actor | Run 1 (start→end) | Run 2 | Run 3 |
|---|---|---|---|
| `vp_operations` | 4.0→6.5 | 4.0→5.0 | 3.0→5.0 |
| `cfo` | 3.0→5.0 | 3.0→5.0 | 3.0→5.0 |
| `it_director` | 2.0→5.0 | 4.0→**3.5** ⬇ | 3.0→4.0 |

| Actor | Cross-run spread | What it means |
|---|---|---|
| `cfo` | 0.0 | The CFO's response is structural — same objection arc every time. Pricing + lock-in. Predictable. |
| `vp_operations` | 1.5 | Moderate — VP's enthusiasm shifts based on specific examples the founder happens to give. |
| `it_director` | **3.5** | High variance — in Run 2 the IT Director actively pulled the deal *backwards* (-0.5). In Run 1 they ended up engaged. The persona's response is unstable; one specific phrasing of "security architecture" makes or breaks the call. |

And the actual final turns from each run diverge concretely:

- **Run 1**: IT Director asks about "joint encryption key arrangement and container deployment specifics"
- **Run 2**: IT Director demands "NIST 800-171 compliance evidence" and stalls
- **Run 3**: IT Director "won't sign off on technical integration until full security documentation review"

This is the simulation property exo provides: **the same setup explores
different conversational paths, surfacing which actors are stable vs which
are highly path-dependent.** Run it 5–10 times for a rehearsal that
matters; the high-variance actors are the ones to prepare hardest for.

**Honest framing**: each actor self-reports its signal values at each turn. These are LLM outputs, not measurements of an external ground truth. The variance is real (you can verify by running it yourself); the *calibration* against actual stakeholder behavior is unproven. Treat outputs as rehearsal hypotheses to stress-test in reality, not as predictions to act on directly.

[Full transcripts of all 3 runs](./examples/sales-pipeline-rehearsal/).

## What actually ships in v0.1

**One polished template + two real experiment results.** Honesty over inventory.

| Asset | What | Status |
|---|---|---|
| `templates/sales-pipeline/` | 4-actor B2B sales rehearsal with hand-polished personas | Shipped, 3 real runs in `examples/` |
| `experiments/E1-recreate-mirofish/` | 8-actor construction-domain sim, actor cast extracted from a real Mirofish Neo4j graph | Shipped, 3 runs, RESULT.md |
| `experiments/E2-extend-mirofish/` | Adds `regulatory_inspector` to E1 via YAML-only edit, measurable per-actor signal shift | Shipped, 2 runs, RESULT.md |

**Templates planned for v0.2** (not yet shipped — honest about this):
- `social-media-reaction` — OASIS-style public reaction modeling (likely needs CAMEL-AI integration)
- `wedding-vendor-coordination`
- `healthcare-triage`
- `incident-response`

If you build one of these, send a PR.

## What this is NOT

- **Not a LangChain replacement.** LangChain wraps API calls; exo runs full simulations with persistent memory.
- **Not a chatbot framework.** This is for *simulating populations of agents*, not building one conversational assistant.
- **Not production-grade.** v0.1. Treat it like a research toy that happens to be docker-compose-ready.
- **Not opinionated about deploy.** If you want Kubernetes, fork it. If you want a SaaS version, you're holding the wrong thing.

## What's under the hood

`exo` v0.1 is intentionally a thin wrapper. The runtime is ~600 lines of pure Python — a turn-loop, an LLM router (with backends for Ollama / Ollama Cloud / Claude OAuth), and a signal extractor. The memory tiers below are *available* via docker-compose profiles but are not load-bearing in v0.1 simple-chat sims.

- [Neo4j](https://neo4j.com/) — graph DB (opt-in via `--profile graph`)
- [Qdrant](https://qdrant.tech/) — vector DB (opt-in via `--profile vector`)
- [PostgreSQL](https://www.postgresql.org/) — structured records (opt-in via `--profile sql`)
- [Ollama](https://ollama.com/) — local LLM runtime (your machine)
- [Ollama Cloud](https://ollama.com/cloud) — frontier OSS models via API
- [Claude OAuth](https://www.anthropic.com/) — frontier inference via Claude Code (via the `claude` CLI)

For reference: [MiroFish-Offline](https://github.com/nikmcfly/MiroFish-Offline) is a domain-specific multi-agent simulator built on CAMEL-AI + OASIS. exo is a more generic, vendor-neutral substrate — different design choice, narrower runtime, broader domain applicability. exo's v0.1 was *informed by* Mirofish but does not depend on it. If you want OASIS-style Twitter/Reddit simulation specifically, use Mirofish.

## Reproducibility

To verify the variance evidence in the section above:

```bash
git clone https://github.com/MGBuilds9/exo.git
cd exo
pip install -r requirements.txt
export OLLAMA_API_KEY=<your-key>    # or LOCAL_OLLAMA_BASE_URL for fully local
./exo run templates/sales-pipeline/domain.yaml --out run-a
./exo run templates/sales-pipeline/domain.yaml --out run-b
./exo run templates/sales-pipeline/domain.yaml --out run-c
diff <(jq -r .signals run-a/transcript.jsonl) \
     <(jq -r .signals run-b/transcript.jsonl)
```

Same template, three different conversations, measurable cross-run variance.

## License

Apache 2.0. Build on it. Fork it. Ship a commercial product on top — that's fine.

## Status

v0.1.0. **Experimental.** What this means honestly:

- The CLI works end-to-end against real Ollama Cloud / local Ollama.
- One template ships (`sales-pipeline`); the other 5 listed above are v0.2 work, not v0.1 inventory.
- Two real experiments (`E1`, `E2`) shipped with full transcripts as evidence. N is small (3 baseline + 2 treatment runs); thresholds were chosen ahead of time but the statistical power is appropriate to a v0.1 demo, not a research paper.
- Memory tiers (Qdrant / Neo4j / Postgres) are wired in compose with opt-in profiles but the runtime doesn't yet read/write to them in the templates. v0.2 work.
- The web UI at :5050 is a health endpoint stub only. v0.2 work.
- `claude-oauth` LLM backend is drafted but only `ollama-cloud` and `local-ollama` are battle-tested.

Issues and PRs welcome.

---

<div align="center">
<sub>Built because the gap between "I want to simulate X" and "I have a running multi-agent simulation of X" should be one YAML file, not three months.</sub>
</div>
