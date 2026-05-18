# Phase 3 — Holistic sentiment measurement protocol

**Status:** committed BEFORE the freeze. After E1 + E2 land + commit, we
tag the repo `v0.1.0-rc1`, then run channels A–F **without touching the
artifact between channels**. Any channel that says "would-not-engage"
above threshold fails the freeze; iterate; tag `rc2`; restart.

## The freeze rule

Once `v0.1.0-rc1` is tagged, I cannot modify:
- README.md, Quickstart.md, WHY.md
- LICENSE
- compose.yaml, exo CLI, exo_runtime/, cli/
- templates/, examples/
- experiments/

Iteration between channels = invalidates the streak. The rule the prior
council violated.

## The six channels

### A — Simulated HN front-page comment thread

**Method:** Use exo's own runtime to spin up 8 HN-archetype personas
reacting to "exo just hit the HN front page." Their `comment_quality`
and `upvote_likelihood` signals = HN-shaped verdict.

**Personas (8):** rust-evangelist, AI-cynic, indie-hacker, FAANG-staff-eng,
AI-optimist, MLOps-veteran, OSS-maintainer, security-engineer.

**Pass:** average `upvote_likelihood` ≥ 6/10 AND no persona returns
`would_downvote: true`.

### B — r/selfhosted + r/LocalLLaMA simulated threads

**Method:** Use exo runtime with 6 homelab-tribe personas.

**Personas (6):** docker-hoarder, AGPL-purist, Proxmox-cluster-builder,
homelab-newbie, GPU-tinkerer, privacy-maximalist.

**Pass:** ≥ 5 of 6 give `would_star: true`.

### C — Comparative forced-choice

**Method:** 10 different LLM-as-judge invocations. Each given a different
use case ("multi-stakeholder rehearsal", "sales-call simulation",
"market-reaction modeling", "incident-response drill", etc.) and asked:
*"You need to build this. Choose ONE of: LangChain, LangGraph, CrewAI,
CAMEL-AI, exo. Defend in 100 words."*

**Pass:** exo wins ≥ 4 of 10 forced-choice decisions.

### D — Dogfood: exo critiques exo

**Method:** Use exo to run a sim where actors are 8 power-user personas
who just saw exo on HN. The trigger is "you clicked through to the GitHub
repo and skimmed the README." Their `would_clone` and `would_recommend`
signals = adoption-likelihood verdict.

**Personas:** same as channel A but a different scenario angle
(post-curiosity adoption decision).

**Pass:** average `would_clone` ≥ 6/10.

### E — gstack `/llm-council-adversarial` skill

**Method:** Invoke the gstack skill (available on disk per the system
reminder) with framing "find errors, don't validate." Treats N-of-N
agreement as signal; any dissent triggers investigation.

**Pass:** N-of-N (all judges) agree exo would be adopted.

### F — Statistical sample (n=20)

**Method:** 20 LLM invocations across the 4 council archetypes (5 per
archetype, fresh sessions, rotating wording across the 3 sealed variants
plus 2 new variants we'll commit before channel F runs).

**Pass:** ≥ 16 of 20 (80%) return `would_star + would_share + would_tell`.

## Aggregation

A run-passes-overall iff ALL 6 channels pass independently. One fail =
freeze fails. Iterate, tag rc2, restart all 6 channels.

## Why this is stronger than the prior 4-archetype council

| Property | Prior council | This protocol |
|---|---|---|
| Sample size | 4 judges per run | 20+ per channel; 70+ total across channels |
| Audience diversity | 4 archetypes | 8 HN archetypes + 6 homelab + comparative-against-real-products + dogfood + adversarial council |
| Artifact-freeze | violated (iterated between runs) | strict freeze at rc1; iteration = restart |
| Comparative grounding | none | channel C forces choice between exo and 4 named competitors |
| Adversarial framing | mixed (some prompts said "evaluate") | channel E uses "find errors" framing per gstack skill |

## What I will commit before running

- This PROTOCOL.md (timestamped, SHA-witnessed)
- One template per channel under `sentiment/channel-{A,B,C,D,E,F}/`
- Tag `v0.1.0-rc1` on the artifact

## What I will commit after running

- One report per channel under `sentiment/channel-{X}/REPORT.md` with raw
  judge outputs + pass/fail decision
- An aggregate `sentiment/SUMMARY.md` with the unanimous decision

## Witness

This protocol is sealed at the SHA of the commit introducing it. Channel
reports must reference this SHA. Edits between channels invalidate.
