# Viral-repo corpus analysis

**Sample:** 27 GitHub repos in AI/agent/LLM/dev-tools categories, all created after 2026-02-01 (≤90 days old) with ≥300–1000 stars depending on axis. Pulled 2026-05-18 via `gh search repos`.

**Star range:** 328 – 16,774. Median ~1,200.

**Notably in the sample:** [`nikmcfly/MiroFish-Offline`](https://github.com/nikmcfly/MiroFish-Offline) at 2,187 stars (Michael's own English fork of Mirofish). This confirms the substrate exo is built on has independently proven viral.

## Per-axis aggregate stats

| Property | corpus median | corpus min | corpus max | exo (rc3) | gap |
|---|---|---|---|---|---|
| README chars | 18,938 | 4,500 | ~60k | 23,287 | within range |
| README lines | 467 | 144 | 2,016 | 429 | within range |
| H1/H2/H3 sections | 36 | 15 | 188 | 27 | **exo slightly low** |
| Badges | 1 | 0 | 17 | 3 | fine |
| Code blocks | 12 | 2 | 46 | 9 | slightly low |
| Has image/gif/video | **48% have one** | — | — | **NO** | **biggest gap** |
| Has Quickstart section | 70% | — | — | YES | match |
| Has comparison/feature table | 93% | — | — | YES | match |

## Section heading frequency across corpus

Top 12 (% of corpus that has the section):

| Heading | % | exo has it? |
|---|---|---|
| License | 81% | yes (link) |
| Quick start | 74% | yes |
| Contributing | 41% | yes (CONTRIBUTING.md) |
| Features | 37% | **no** |
| Documentation | 30% | partial |
| Star history | 30% | impossible (no stars yet) |
| How it works | 30% | partial (Architecture section) |
| Architecture | 30% | yes |
| Installation | 26% | partial (in Quickstart) |
| Roadmap | 22% | **no** |
| Prerequisites | 22% | partial |
| Acknowledgements | 19% | **no** |
| Project structure | 19% | **no** |

## License distribution

| License | n | % | Comment |
|---|---|---|---|
| **MIT** | 12 | 44% | modal choice |
| **Apache-2.0** | 7 | 26% | exo's choice |
| none / unspecified | 4 | 15% | risky |
| AGPL-3.0 | 2 | 7% | the more-viral fork pattern |
| GPL-3.0 | 1 | 4% | |
| other | 1 | 4% | |

Apache is the second-most-common viral license — exo is fine here.

## Tagline anatomy from the top 5 by stars

- `QwenPaw` (16,774★): "Your Personal AI Assistant; easy to install, deploy on your own machine or on the cloud; supports multiple chat apps"
- `edict` (15,793★): "三省六部制 · OpenClaw Multi-Agent Orchestration System — 9 specialized AI agents with real-time dashboard, model config..."
- `hive` (10,364★): "Multi-Agent Harness for Production AI"
- `ARIS` (9,896★): "Lightweight Markdown-only skills for autonomous ML research: cross-model review loops"
- `mission-control` (4,863★): "Self-hosted AI agent orchestration platform"

**Pattern: confident-descriptive declarations, not apologetic ones.** "X for Y" or "X with Y" or "[Adjective] [category]." None of them lead with limitations.

Compare exo (rc3): *"A 600-line Python wrapper that runs multi-actor LLM conversations from a YAML file."* This is *deflated* per adversarial council feedback. But against viral pattern, it's apologetic. Need to find the middle ground: descriptive-confident without overclaim.

## What viral repos do that exo doesn't (concrete deltas)

| Delta | Evidence | Priority | Effort |
|---|---|---|---|
| **Add a screenshot / GIF / asciinema cast** | 48% of corpus has one; none of the top-5 are text-only | HIGH | 30 min |
| **Rewrite tagline confident-descriptive** | None of the viral repos lead with self-deprecation | HIGH | 10 min |
| **Add Features section** | 37% have one | MED | 15 min |
| **Add Roadmap section** | 22% have one (collects v0.2 promises) | MED | 15 min |
| **Add Acknowledgements section** | 19% have one; credits CAMEL/OASIS/Mirofish honestly | MED | 10 min |
| **Add Project Structure section** | 19% have one | LOW | 10 min |
| **Add Star history badge** | 30% have one — impossible until public + has stars | DEFER | (future) |

## Synthesis — what the corpus signals about "going viral"

1. **Visual evidence matters at scale.** Half the corpus has a screenshot, GIF, or video right under the tagline. Text-only README + text-only example transcript is a structural gap, not a stylistic preference.
2. **Confident-descriptive >> apologetic-honest.** Viral READMEs don't apologize for v0.1 in the headline; they save honesty for the Status section. exo's rc3 deflation work was right per adversarial feedback but **over-corrected** the tagline.
3. **The standard section anatomy is dense.** Median 36 H1/H2/H3 sections; exo has 27. Adding Features / Roadmap / Acknowledgements / Project Structure brings exo into the corpus median.
4. **Apache is fine.** MIT is more common but Apache is well-represented (26%) and *more* permissive than AGPL (which only 7% used). License is not a viral-blocker.
5. **The corpus includes Michael's own fork.** Mirofish-Offline at 2,187 stars is in this sample. exo is positioned as a generalization of Mirofish's pattern — that's a defensible viral position.

## What this analysis does NOT prove

- That applying these deltas WILL make exo go viral. Correlation in 27 examples is suggestive, not causal.
- That viral repos went viral because of these patterns. Confounding: the underlying *idea* matters more than the README anatomy.
- That the corpus is representative of the broader OSS-viral population. We filtered to AI/agent/LLM in Python (where exo lives) and stars >300; a different cohort would yield different patterns.

## Recommended action

Apply the 4 HIGH/MED priority deltas (tagline, Features, Roadmap, Acknowledgements) as a single rc4 commit. **Skip the GIF/screenshot for now** (requires manual screen capture; defer to launch prep). Re-run the sentiment channels against rc4 when Ollama Cloud rate-limit resets.

Expected result: rc4 tagline-confidence + added sections moves the artifact closer to viral-cohort anatomy *without* re-introducing the overclaims that adversarial caught in rc1.
