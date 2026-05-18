# Mirofish experiment plan

**Status:** draft for Michael's review BEFORE execution
**Reason for writing this first:** prior council runs violated contract §4
(experiments were supposed to run before the council). Rather than vibe-run
the experiments now, this plan ensures: (a) experiments are designed
against falsifiable hypotheses, (b) resource constraints are explicit,
(c) we capture *how to develop this kind of thing*, not just results.

## What I actually learned about Mirofish

(Reading the source code, not vibes.)

| Claim | What I verified | Source |
|---|---|---|
| Mirofish is a multi-agent simulator | YES | `app/services/simulation_runner.py` |
| It simulates SOCIAL-MEDIA (Twitter/Reddit), not general stakeholder convos | **Key correction**: `PlatformType.TWITTER \| REDDIT` enum + OASIS library underneath | `app/services/simulation_manager.py:25-30` |
| Construction-domain entities ARE the actor cast | YES — the 55 Entity nodes in Neo4j include KrewPact, MDM Group Inc., ProjectManager, ClientExecutive, etc. | Neo4j `MATCH (e:Entity)` query |
| Workflow: ingest text → build graph → generate profiles → run sim → report | YES | `app/api/simulation.py` route map: `/create` → `/prepare` → `/generate-profiles` → `/start` → `/run-status` → `/posts` + `/comments` + `/interview` |
| Embeddings via BERTHA llama-swap (qwen3-embedding-4b, 2560-dim) | YES — entities in Neo4j have 2560-element embedding arrays | `properties(e).embedding` length check |
| LLM via Ollama on host (default qwen2.5:32b) | YES per `.env.example` | `LLM_BASE_URL=http://localhost:11434/v1` |
| 8 projects + 9 simulations exist | **No** — bind mount is empty. Disk artifacts wiped during the 2026-05-13 archive event. Only Neo4j graph survives. | `ls backend/uploads/` returns nothing |

The graph is the authoritative reference. Disk simulations are gone.

## Why I can't just re-run Mirofish fresh

Three blocking resource gaps:

1. **BERTHA llama-swap on :1234 is offline.** Mirofish needs it for embeddings (`EMBEDDING_BASE_URL=http://localhost:1234/v1`). Starting BERTHA isn't in my scope without instructions from Michael.
2. **qwen2.5:32b is not pulled locally.** Ollama on :11434 has 4 models (gemma4, gemma3:1b, bge-m3, all-minilm) — none are qwen2.5. Pulling qwen2.5:32b is ~20GB download + needs ~24GB VRAM to run well; my 24GB free RAM headroom doesn't include GPU VRAM (no nvidia-smi visible from this shell).
3. **Embedding-dimension mismatch.** Mirofish's existing Neo4j embeddings are 2560-dim (qwen3-embedding-4b). Ollama's default embedding (nomic-embed-text) is 768-dim. Cannot directly query the existing graph with a different embedding model — vector dim must match.

This means experiments must reference the SURVIVING data (Neo4j graph), not require new Mirofish runs.

## Resource snapshot (verified)

- 62.9 GB total RAM, 24 GB free → headroom for exo runs (which are LLM-bound, not memory-bound)
- 713 GB free on C: → plenty
- Mirofish containers using ~1 GB combined → keep them up (they aren't fighting for resources)
- Local Ollama models: gemma4:latest (9.6GB), gemma3:1b (1.0GB), bge-m3 (1.2GB embedding), all-minilm (0GB cached)
- Ollama Cloud API key verified callable

Resource budget per exo experiment run:
- ~2 minutes wallclock for a 20-turn 4-actor sim
- ~$0.02 in Ollama Cloud tokens
- ~0 local GPU / RAM impact (calls go to cloud)

Total experiment budget: **~10 minutes wallclock + ~$0.10 tokens** for E1 + E2 with 3-5 runs each.

## The experiments

### E1 — RECREATE
**Hypothesis:** exo can replicate Mirofish's multi-actor construction-domain
*conversation* pattern with the same actor cast, but will NOT replicate
Mirofish's OASIS-specific Twitter+Reddit features (post/comment threading,
virality propagation, network influence).

**Methodology:**
1. Extract the actor cast from Mirofish's Neo4j graph
   ```cypher
   MATCH (e:Entity) RETURN e.name, e.summary, e.attributes_json
   ```
   Filter to entities whose `summary` indicates a role (ProjectManager,
   FieldForeman, Estimator, FinanceAdmin, Executive, SkepticalEmployee,
   ClientExecutive, Subcontractor).
2. Build a `mirofish-recreate/domain.yaml` with those entities as actors.
3. Build a `mirofish-recreate/scenario.yaml` with a trigger event in
   Mirofish's actual problem space: *"MDM Group Inc. announces migration
   from ERPNext to KrewPact in a company-wide meeting. Each stakeholder
   reacts."* (Uses the actual entity names from the graph.)
4. Run with `exo run` — 5 rounds, 8 actors = up to 40 turns.
5. Run 3 times to assess variance (same protocol as sales-pipeline).

**Falsifiable pass criteria:**
- ✅ exo loads the entity list without manual cleanup beyond a 30-line YAML
- ✅ Actors speak in-character with construction-domain vocabulary
  (KrewPact, ERPNext, project lifecycle, takeoffs) > 60% of turns
- ✅ Cross-run signal variance per actor > 0 (proves emergence, not template)
- ✅ Total time-to-first-transcript < 30 minutes

**Falsifiable failure modes:**
- ❌ Actors speak generically (talk about "the migration" without
  referencing ERPNext, KrewPact, MDM-specific concerns)
- ❌ Run crashes or hits rate limits
- ❌ Time-to-first-transcript > 1 hour

**Honest gaps (what we WON'T claim):**
- Mirofish-specific features (Twitter post structure, comment threading,
  influence propagation, virality scoring) are not in exo's runtime.
  Don't claim equivalence on those.
- We will not produce posts or comments in OASIS schema — exo's output is
  a turn-based conversation transcript.

### E2 — EXTEND
**Hypothesis:** Adding a new actor type to a Mirofish-style sim via exo is
faster than via Mirofish itself, AND the new actor measurably changes the
behavior of the existing actors.

**Methodology:**
1. Add a new actor to `mirofish-recreate/domain.yaml`:
   ```yaml
   - id: regulatory_inspector
     persona: |
       Provincial labour-safety inspector. Cold-arrival. Has authority
       to halt operations. Reads project records line-by-line. Skeptical
       of "we'll fix it later" promises.
     role: regulator
     model: ollama-cloud/qwen3-coder:480b
   ```
2. Modify the scenario trigger: *"Mid-meeting, a labour-safety inspector
   shows up unannounced and asks for documentation evidence on the
   migration."*
3. Run the modified scenario 2 times.
4. Compare: same 8 original actors' signal trajectories WITH inspector
   present vs WITHOUT (i.e., compare E2 runs against E1 runs).

**Falsifiable pass criteria:**
- ✅ Time-to-modify: < 10 minutes (YAML edit only, no code changes)
- ✅ ≥ 2 of the original 8 actors' `sentiment` or `trust` signal trajectories
  differ by > 1.5 between WITH-inspector and WITHOUT-inspector runs
- ✅ The inspector actor produces in-character regulator content (not
  generic "I have concerns")

**Falsifiable failure modes:**
- ❌ Modification requires editing Python code or compose files
- ❌ All 8 original actors behave identically with/without inspector
- ❌ Inspector's persona collapses to generic "stakeholder #9"

### E3 — already done
The sales-pipeline template + 3 runs of variance evidence in
`examples/sales-pipeline-rehearsal/` IS Experiment 3 (novel domain
beyond Mirofish's construction). No new work needed.

## How to read the results

**If E1 and E2 both pass:** exo demonstrably fills the "multi-actor
conversation simulation" niche that Mirofish handles for social-media,
generalized to any domain. We can credibly claim "exo is what you use
when you want Mirofish's *idea* (multi-actor reaction to an event) but
your domain isn't Reddit."

**If E1 passes but E2 fails:** exo handles static actor casts but
extension is harder than the YAML claim — known gap, document it.

**If E1 fails:** the actor-cast pattern doesn't work because exo's
prompt-based persona system isn't enough to maintain consistent
construction-domain vocabulary across 8 actors / 40 turns. Surface this
as a known limitation. Decide if memory-tier (graph) is needed.

## What this teaches us about how we develop "things like that"

(Michael's meta-ask. Captured here so the learnings outlive these specific
experiments.)

1. **Investigate the substrate before designing the test.** I lost a real
   hour assuming Mirofish was general multi-agent. The code clearly said
   `PlatformType.TWITTER | REDDIT`. Read the source.
2. **Find the authoritative reference, not the convenient one.** I almost
   designed E1 around "compare to Mirofish's docs" — but the docs are
   marketing surface. The Neo4j graph + the API contract are the real
   reference.
3. **Make hypotheses falsifiable BEFORE running.** "It should work" is
   not a pass criterion. "Construction-domain vocabulary > 60% of turns"
   is one.
4. **Account for what you can't compare on.** I will NOT claim exo
   matches Mirofish's OASIS Twitter-virality features. That's not in
   exo's runtime. Pretending equivalence is the same vibe-coding I'm
   trying to avoid.
5. **Resource constraints are the experiment's frame.** BERTHA being
   down + qwen2.5 not pulled limited what was feasible. The experiment
   plan adapted to the constraint rather than ignoring it.
6. **Variance > average.** Cross-run variance is what proves
   non-determinism. Single-run outputs can be cherry-picked; 3-run
   variance can't.

## What I'll commit before running

- This PLAN.md (committed before any experiment runs)
- A pre-run snapshot of system state (RAM/disk/Mirofish container health)
- The exact Cypher query used to extract actors

## Estimated time + cost

- Reading + planning (done): ~30 min
- E1 build + 3 runs: ~30 min, ~$0.06 Ollama Cloud
- E2 build + 2 runs: ~20 min, ~$0.04 Ollama Cloud
- Synthesis writeup: ~30 min
- **Total: ~2 hours, ~$0.10 in tokens, zero local GPU pressure**

## Awaiting Michael's green-light on this plan before execution

Specifically asking you to verify:
1. Is the "compare against Neo4j-surviving actors, don't re-run Mirofish" approach acceptable? (vs you starting BERTHA + me pulling qwen2.5 — which adds hours)
2. Is the scope (E1 + E2, with E3 already done) what you wanted?
3. Any of the hypotheses you'd sharpen or change?
