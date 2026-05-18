# sales-pipeline

Rehearse a multi-stakeholder B2B sales conversation before the real meeting.

## When to use this

You're about to walk into a 30-minute discovery call with three decision-
makers. You've done one demo. You don't know what's going to come up. You
want to know *before* the call lands what objections you'll hit.

## Cast

| Actor | Role | Cares about |
|---|---|---|
| `founder` | seller | Closing the pilot, not over-explaining the tech |
| `vp_operations` | prospect-decider | "Show me the workflow where this saves six hours per week" |
| `cfo` | prospect-financial | Pricing, contracts, vendor lock-in, build-vs-buy |
| `it_director` | prospect-technical | On-prem, security, patch cadence |

## Run

```bash
# From the exo repo root
exo run templates/sales-pipeline/domain.yaml

# Or copy and customize first
cp -r templates/sales-pipeline my-rehearsal
cd my-rehearsal
# Edit personas in domain.yaml to match YOUR actual prospects
exo run domain.yaml
```

## What you get

A 20-turn transcript where the founder pitches and three prospects probe. Each
actor reports their `prospect_interest`, `trust`, and `deal_momentum` per
turn. The summary surfaces the trend — were objections answered, or did
momentum stall?

## What to do with it

Before the real call:
- Watch which objections show up that you weren't prepared for
- Notice which prospect role is the hardest sell
- See how your pitch reads when stripped of your own framing

After the real call:
- Re-run with the prospects' actual statements as additional personas
- Diff predicted-vs-actual to tune the template for the next prospect

## Customize

The four personas in `domain.yaml` are sketched generically. To rehearse a
specific deal, replace the persona text with what you actually know about
your prospect's company:
- VP Ops: their LinkedIn + their company's tech stack on BuiltWith
- CFO: their recent earnings commentary (if public) or industry priors
- IT Director: their job postings (what stack are they hiring for?)

The more specific, the more useful the rehearsal.
