# Example: sales-pipeline rehearsal

This is a real 20-turn run of `templates/sales-pipeline` against
Ollama Cloud (qwen3-coder:480b) on 2026-05-18.

The founder is pitching a B2B AI platform to three prospects (VP Ops, CFO,
IT Director). Each prospect probes from their angle: workflow value,
financial structure, technical implementation.

**Total run time:** ~140 seconds for 20 turns across 4 actors.
**Cost:** ~$0.02 in Ollama Cloud tokens.

## Read the transcript

```bash
cat transcript.jsonl | jq -r '"[\(.turn)] \(.actor_id) (\(.role // "?")): \(.content[:200])"'
```

## What to notice

- Each prospect role surfaces objections specific to their function. The
  CFO never asks about Docker; the IT Director never asks about pricing.
- The founder's persona ("over-explains technology, anxious about quarter
  end") shows up in the response cadence — longer answers, slightly
  defensive when challenged.
- The `deal_momentum` signal (in summary.md) trends down over the call,
  matching the realistic dynamic where a discovery call rarely closes
  itself.
- This is one run with one set of model temperatures. Re-running produces
  different specific objections; the *shape* of the call stays similar.

## How to re-run

```bash
cp -r templates/sales-pipeline my-rehearsal
cd my-rehearsal
# Edit domain.yaml personas to match YOUR prospects
exo run domain.yaml
```
