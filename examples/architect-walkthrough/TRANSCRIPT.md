# Example: `exo architect` walkthrough transcript

This is what running `exo architect` on a real machine looks like. The
architect first scans your hardware + services (the "doctor" step), then
asks ~12 questions, then writes a `domain.yaml` + `scenario.yaml` that
uses YOUR actual resources.

This transcript was captured on 2026-05-18 on Windows 11 / 24-core / 62.9 GB RAM
/ AMD Radeon RX 7900 XT / Mirofish Neo4j running on localhost.

---

```
$ ./exo architect --name customer-support-sim

┌─────────────────────────────────────────────────────────────────────────────┐
│ exo architect — design a multi-agent simulation tailored to YOUR machine.   │
│ Step 1: scan your hardware + services + accounts.                           │
│ Step 2: 12 questions about the simulation.                                  │
│ Output: a domain.yaml that uses what you actually have, not generic         │
│ defaults.                                                                   │
└─────────────────────────────────────────────────────────────────────────────┘

Step 1. Scanning your machine for hardware + services...
  OS: Windows (10) on AMD64
  CPU: 24 cores
  RAM: 62.9 GB total (18.8 GB free)
  Disk: C:\: 707.5 GB free, M:\: 182.4 GB free
  GPU: AMD Radeon RX 7900 XT
  
  Local services:
    [+] Ollama (http://127.0.0.1:11434/api/tags) — 5 model(s): qwen3-coder:480b-cloud, gemma4:latest, bge-m3:latest, all-minilm:latest, gemma3:1b-it-qat
    [-] LM Studio/llama-swap (http://127.0.0.1:1234/v1/models) — status 401
    [-] Qdrant — not reachable
    [+] Neo4j (http://127.0.0.1:7474)
    [-] Postgres — not reachable
    [-] SearXNG — not reachable
    [+] Docker daemon — 29.4.3
    [+] Claude Code CLI — 2.1.143 (Claude Code)
    [+] Ollama CLI — ollama version is 0.23.4
  
  Cloud accounts (from environment):
    [+] Ollama Cloud (OLLAMA_API_KEY) — frontier OSS models via API
    [-] OpenAI (OPENAI_API_KEY)
    [-] Anthropic (ANTHROPIC_API_KEY)
    [-] Google AI / Cohere / Together / Replicate / HF — not configured

Q-pre-1. Any other machines I should probe? (homelab IP, NAS, Proxmox node)
> 192.168.0.19

Probing 192.168.0.19...
    [-] @192.168.0.19 Ollama — connection refused
    [-] @192.168.0.19 Qdrant — connection refused
    [+] @192.168.0.19 Neo4j (http://192.168.0.19:7474) — reachable
    [-] @192.168.0.19 LM Studio/llama-swap — not reachable

Q-pre-2. Any cloud accounts not in env vars? (Vercel team, Modal, Fly.io, etc.)
> Vercel team, Cloudflare

Q1. Working name for this simulation [kebab-case] [my-sim]: customer-support-sim
Q2. In one sentence, what does this simulation answer for you?
> Predict how our customer-support team responds when a high-value customer goes through a billing dispute

Q3. What kind of system are you simulating?
  1. Social platform (Reddit/Twitter-style reactions)
  2. Organizational stakeholders (boardroom, project team, contract dispute) (default)
  3. Market dynamics (pricing, supply/demand, negotiation)
  4. Customer service / sales interaction
  5. Healthcare triage / clinical reasoning
  6. Incident response (on-call, escalation, resolution)
  7. Custom — I'll describe it
Choose: 4

Q4. How many actors? small (3-8) / medium (10-30) / large (50-200): small

Q5. What memory does the simulation need?
  1. Just conversation history — actors remember what was said (default)
  2. Conversation + relationships between actors
  3. Conversation + a shared knowledge corpus actors can retrieve from
  4. Conversation + relationships + knowledge corpus + structured records
Choose: 1

Q6. Where should LLM inference go?
  1. Claude OAuth (frontier intelligence; uses your Claude Code login)
  2. Ollama Cloud (cloud OSS frontier) (default)
  3. Local Ollama / llama-swap (zero cost, smaller models)
  4. Mixed: frontier for hard actors, local for simple ones
Choose: 1     [→ architect overrides this with the doctor's recommendation:
              claude-oauth detected, used as primary]

Q7. How many turns per actor [6]: 5
Q8. What's the trigger event that starts the simulation?
> Customer calls in disputing a $4,200 charge they say was unauthorized. They are on the verge of churning.

Q9. How deterministic should the simulation be? (0..1) [0.7]: 0.7
Q10. What signals should the runner track per turn? [sentiment,trust,commitment]
> sentiment,trust,resolution_likelihood
Q11. Stop after how many total turns [12]: 20
Q12. Transcript format [jsonl]: jsonl

┌─────────────────────────────────────────────────────────────────────────────┐
│ ✓ Designed.                                                                 │
│                                                                             │
│   customer-support-sim/domain.yaml   (4 actors, memory=none)                │
│   customer-support-sim/scenario.yaml                                        │
│   customer-support-sim/README.md                                            │
│                                                                             │
│ Run with:                                                                   │
│   cd customer-support-sim && exo run domain.yaml                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Generated `domain.yaml` (auto-output)

The architect picked `claude-oauth` for each actor because the doctor
detected Claude Code CLI on this machine. If Claude OAuth weren't
available, it would have fallen back to `ollama-cloud/qwen3-coder:480b`
(because OLLAMA_API_KEY was set) or `local-ollama/<best-model>` as a
last resort.

```yaml
name: customer-support-sim
purpose: Predict how our customer-support team responds when a high-value customer goes through a billing dispute
created_by: exo-architect v0.1.0 (hardware-aware)
system_kind: customer-service
scale: small
memory:
  tier: none
  vector_backend: none
  graph_backend: none
  sql_backend: none
actors:
  - id: customer
    persona: Frustrated, deadline-pressured, has prior negative experiences
    role: customer
    model: claude-oauth
  - id: agent
    persona: Service-oriented, follows scripts, has authority for $X concessions
    role: agent
    model: claude-oauth
  - id: supervisor
    persona: Escalation target, watches metrics, defends company position
    role: manager
    model: claude-oauth
runtime:
  default_model: claude-oauth
  fallback_model: ollama-cloud/qwen3-coder:480b
  llm_preference: claude-oauth
  temperature: 0.7
  parallel_agents: 3
  log_level: INFO
machine_profile:
  scanned_at: '2026-05-18T19:00:00+00:00'
  os: Windows 10.0.26200
  ram_gb: 62.9
  gpu: AMD Radeon RX 7900 XT
  extra_hosts_probed: ['192.168.0.19']
  extra_cloud_accounts: ['Vercel team', 'Cloudflare']
  doctor_notes:
    - Claude Code CLI detected — claude-oauth available for frontier-quality actors
    - OLLAMA_API_KEY set — Ollama Cloud frontier-OSS models available
    - Local Ollama @ :11434 has 3 chat model(s); using qwen3-coder:480b-cloud as local fallback
    - Local embedding model available: bge-m3:latest
    - No Qdrant detected — recommend Chroma embedded (zero ops)
    - Neo4j detected @ http://127.0.0.1:7474 — graph layer ready
    - No Postgres detected — SQLite embedded is fine for personal sims
```

## What the architect did that's different from "fill in this template"

1. **Detected what's actually available.** It found Claude Code, Ollama, and Mirofish's Neo4j on this machine.
2. **Probed an additional host the user provided.** Neo4j on `192.168.0.19` was reachable — captured.
3. **Recorded cloud accounts the user listed.** Vercel team + Cloudflare noted in `machine_profile.extra_cloud_accounts` even though no env var probe found them.
4. **Overrode the user's stated preference with reality.** User said "Claude OAuth" in Q6; doctor confirmed it was available; if it hadn't been, architect would have substituted the best detected fallback automatically.
5. **Persisted the "why" alongside the "what."** Every YAML output carries a `machine_profile` block with `doctor_notes` so 3 weeks later you can audit why the config picked what it did.

That's the value-add. The template stays generic; the actual generated config is *specific to this machine on this date*.
