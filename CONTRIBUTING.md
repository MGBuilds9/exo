# Contributing to exo

Short doc. The project is small (~600 lines runtime, ~300 lines CLI); easy to contribute to.

## Quick start for contributors

```bash
git clone https://github.com/MGBuilds9/exo.git
cd exo
pip install -r requirements.txt
python tests/test_architect_determinism.py   # should print "7/7 passed"
```

## What contributions are most welcome

In rough priority order:

1. **New templates** — copy `templates/sales-pipeline/` and adapt for your domain. Send a PR with a working `domain.yaml` + `scenario.yaml` + a one-page `README.md` describing the use case. We need: healthcare-triage, wedding-vendor-coordination, incident-response, social-media-reaction.

2. **Memory tier wiring in the runtime** — v0.1 has Qdrant/Neo4j/Postgres in `compose.yaml` but the runtime doesn't actually use them yet. If you want to wire vector retrieval, graph entity lookup, or structured-record write into the turn-loop, that's the most load-bearing single contribution.

3. **Claude OAuth backend testing** — `exo_runtime/llm_router.py` has a `_call_claude` method that's drafted but not battle-tested. If you run Claude Code, test it and PR fixes.

4. **CI** — there's a minimal GitHub Action at `.github/workflows/test.yml` that runs the determinism test. More tests welcome (especially around the LLM router error paths and the doctor's hardware-detection fallbacks).

5. **Doctor expansion** — add probes for more local services (Redis, Elasticsearch, MinIO, etc.), more cloud providers (Modal, Together, Replicate inference APIs), or better GPU detection on Apple Silicon and AMD.

6. **Sentiment / evaluation tooling** — the `sentiment/` directory has the rc1/rc2 channel dispatchers. They have known issues (rate-limit handling, parallel-dispatch sensitivity). Improvements welcome.

## What's NOT in scope for v0.1

- A web UI (planned for v0.2)
- CAMEL-AI or OASIS integration (planned for v0.2; v0.1 deliberately ships a thin Python turn-loop)
- Production-grade observability (out of scope for an experimental kit)
- Calibration of self-reported signals against ground truth (research-level work; out of scope for the bundle)
- Templates for domains we don't have personal experience in (we'd rather have someone else's lived expertise in those PRs)

## PR checklist

- [ ] Run `python tests/test_architect_determinism.py` — must pass 7/7
- [ ] If adding a template: include a `README.md` explaining the use case + run it once and commit the transcript as evidence
- [ ] If changing the architect: add a determinism test for the new recommendation function
- [ ] Update `README.md` if your change is user-facing
- [ ] One commit per logical change; squash before merge if you'd like

## Code style

- Python 3.11+ type hints where useful, not religiously
- No black/ruff configuration committed (yet) — write reasonable Python
- Docstrings for public functions in `exo_runtime/`; comments only where the why is non-obvious
- YAML configs hand-readable: `safe_dump(sort_keys=False)`

## Reporting bugs

Open an issue. Include:
- `python exo doctor --json` output (the hardware + service report)
- The `domain.yaml` you were running (with secrets redacted)
- The error message + first 10 lines of stack trace
- What you expected vs. what happened

## Governance

This project is maintained by Michael Guirguis. License is Apache 2.0; the project welcomes forks. There is no formal governance committee in v0.1; if usage grows, that'll change.

## Talk to us

- GitHub issues for bugs + feature requests
- GitHub Discussions for "should exo do X?" questions
- No Discord / Slack yet (deliberate — keeping signal in public threads)
