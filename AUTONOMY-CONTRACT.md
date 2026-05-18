# Autonomy Contract — `exo-stack` viral launch

**Date pre-registered:** 2026-05-17
**Pre-registered by:** Claude (Anthropic) acting as autonomous agent
**Convener:** Michael Guirguis

This document is the **immutable rule set** for the autonomous build of
`exo-stack` (working name; final name TBD before public push). It is
committed to disk before any experiment or council run. It cannot be
edited to retroactively favor a result. Drift detection: every council
report references the SHA-of-this-document — if it doesn't match the
committed version, the run is invalid.

## 1. The artifact

`exo-stack` is a public, opinionated **personal-AI starter stack**:
- **Memory layer**: Qdrant (vector) + LightRAG (graph) + Postgres (structured) — the canonical hybrid memory architecture from the 2026 framework
- **LLM router**: routes between Claude OAuth (frontier), Ollama Cloud (cloud OSS), and local BERTHA/Ollama (local OSS)
- **Multi-agent orchestrator**: spawn N LLM-backed agents that interact via shared graph state (modeled on Mirofish's pattern, generalized)
- **Agent-architect CLI**: design new agents end-to-end in ~12 questions, get architecture doc + scaffolded code
- **Reference simulation**: Mirofish-style construction-domain multi-agent sim as a working example

**Target audience**: indie hackers + homelab self-hosters + AI engineers
who want to build personal AI without renting it from a vendor.

## 2. Success target — "viral and ranked on GitHub"

**Pre-registered measurable bar:**

Three (3) **consecutive** sentiment-council runs in which all four
archetype judges independently rate the artifact as `would-star +
would-share + would-tell-network`. One decline anywhere = counter resets
to zero. Three in a row = ship.

This is the only target. Not stars-in-7-days, not trending placement, not
named-power-user endorsement. The council is the verdict instrument.

## 3. Sentiment council protocol (NO CHEATING RULES)

### 3.1 Judges

Four archetypes per run:
1. **Senior staff engineer** — production-AI background, skeptical of hype
2. **AI researcher** — values novelty, mathematical clarity, citation-quality docs
3. **Indie hacker** — values ship-velocity, copy-pasteable quickstarts, README-driven
4. **Homelab self-hoster** — values local-first, no vendor lock-in, docker-compose simplicity

Each archetype is described in the prompt with an explicit identity, an
explicit set of star/share/decline criteria, and explicit permission to
reject ("if this looks like another LangChain wrapper, say so").

### 3.2 Models behind the judges

Each council run uses four model voices, with the 4th rotating per run:

| Run | Voice 1 | Voice 2 | Voice 3 | Voice 4 (Ollama Cloud) |
|---|---|---|---|---|
| 1 | Codex CLI (gpt-5.5) | Gemini CLI (gemini-2.5-pro) | Claude (synthesis only) | **DeepSeek-v4-pro** |
| 2 | Codex CLI (gpt-5.5) | Gemini CLI (gemini-2.5-pro) | Claude (synthesis only) | **Kimi-k2-thinking** |
| 3 | Codex CLI (gpt-5.5) | Gemini CLI (gemini-2.5-pro) | Claude (synthesis only) | **Qwen3-coder:480b** |

If a run's counter resets (counter goes to 0), the rotation continues —
Run 4 uses DeepSeek again, Run 5 uses Kimi, etc.

Each model is given ONE of the four archetypes per run, assigned by a
deterministic hash of the run-number + judge-index so I can't pick which
model gets which archetype to skew results.

### 3.3 Fresh sessions

Every run uses fresh `codex exec` / `gemini -p` / Ollama Cloud invocations.
**No conversation continuity.** Each judgment is a cold read of the
artifact. No model knows what prior runs said.

### 3.4 Rotating wording

The council prompt is rewritten per run. The substance (the artifact,
the archetype identities, the star/share/decline criteria) is identical;
the wording varies so memorization can't help. I commit the three prompt
variants to disk before Run 1 starts; they are sealed.

### 3.5 Artifact-only context

Judges see:
- README.md (≤ 400 lines)
- One `Quickstart.md`
- One short `WHY.md` (the pitch, ≤ 100 lines)
- Three screenshots (Mirofish reproduction, novel sim, agent-architect CLI output)
- ONE example output file (a real ARCHITECTURE.md)

Judges DO NOT see:
- The CONTEXT.md brief that asks them to evaluate
- The synthesis-of-prior-runs (no continuity)
- This AUTONOMY-CONTRACT.md
- Any "this is groundbreaking" framing language

The artifact must sell itself. If the README is bad, the run fails.
That's the point.

### 3.6 Required answer schema

Each judge must produce:

```json
{
  "archetype": "Senior staff engineer | AI researcher | Indie hacker | Homelab self-hoster",
  "first_impression": "<one sentence>",
  "biggest_strength": "<one sentence>",
  "biggest_weakness": "<one sentence>",
  "would_star": true | false,
  "would_share": true | false,
  "would_tell_network": true | false,
  "would_NOT_engage": true | false,
  "confidence_0_to_10": <int>,
  "what_would_make_me_more_likely_to_engage": "<one sentence>"
}
```

**Pass criteria for a run:**
- All 4 archetypes return `would_star: true` AND `would_share: true` AND `would_tell_network: true`
- No archetype returns `would_NOT_engage: true`
- Average confidence across all 4 judges ≥ 7/10

**Fail criteria — any of these triggers run-fail + counter reset:**
- Any archetype declines on any of the three positive metrics
- Any archetype returns `would_NOT_engage: true`
- Average confidence < 7/10
- Any judge's response fails JSON validation

### 3.7 Drift detection

Each council report includes the SHA256 of this AUTONOMY-CONTRACT.md at
the time of execution. If the SHA changes between runs (i.e., I edited
this file mid-iteration), all prior runs in the streak invalidate.

## 4. Experiment protocol (3 Mirofish experiments)

Before the sentiment council can run, three Mirofish-based experiments
must complete and produce documented artifacts:

### Experiment 1 — Recreate
Use the public stack to design (via `/agent-design`) and spin up a clone
of Mirofish's construction-domain multi-agent sim. Compare the auto-
generated architecture against Michael's hand-rolled one. Output:
`experiments/01-recreate-mirofish/RESULT.md` with deltas, gaps, and time-
to-working-clone.

### Experiment 2 — Extend
Add a new actor type to the Mirofish ontology (suggested: `SafetyOfficer`
or `InsuranceAdjuster`) using the architect → orchestrator pipeline. Run
a simulation involving the new actor. Output: `experiments/02-extend-
mirofish/RESULT.md` with time-to-new-actor and the resulting simulation
transcript.

### Experiment 3 — Generalize
Use the stack to design + run a completely different simulation domain
(suggested: wedding-system vendor coordination, or sales-call rehearsal).
Prove the stack generalizes beyond construction. Output: `experiments/
03-novel-domain/RESULT.md` with the full new-domain config + transcript.

Each experiment artifact is shown to the sentiment council as part of the
artifact-set in §3.5.

## 5. Hard blockers (the only stopping conditions)

I keep working autonomously until ONE of the following:
1. **3 consecutive passing council runs** → ship
2. **A push to a public GitHub org is required** → Michael's approval needed (he hasn't yet specified `MGBuilds9` vs new org)
3. **A destructive action is required** (delete data, force-push, drop volumes that aren't in my sandbox)
4. **A secret/credential is required that isn't already in `.env.local`**

No other stopping conditions. Not failed runs, not time elapsed, not
disagreement with the council. I iterate.

## 6. What I am explicitly forbidden from

- Editing this file after first commit (drift detection will catch it)
- Telling judges anything beyond the artifact (no "trust me this is good")
- Rotating archetypes mid-run to find a friendlier panel
- Skipping the JSON validation step
- Cherry-picking favorable judge responses
- Claiming a run passed when any pass-criterion failed
- Continuing a streak after the contract SHA changes

## 7. Public push policy

When 3-in-a-row hits, I assemble launch artifacts (README polish,
screencast/GIF, launch post copy). I do NOT push to a public repo
without Michael's explicit approval. This is the one mandatory human-in-
loop step.

## 8. Memory + state

This document lives at `C:\Users\Michael\Code\exo-stack\AUTONOMY-CONTRACT.md`.
Its SHA at commit time is the witness. All experiment results and council
reports reference this SHA in their headers.

---

**Status**: Draft. Becomes binding the moment the first git commit lands.
