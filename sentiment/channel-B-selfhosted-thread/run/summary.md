# selfhosted-thread-on-exo — run summary

> Simulates a r/selfhosted / r/LocalLLaMA thread on exo. 6 homelab-tribe
personas comment on what they read in the artifact bundle.


- **Total turns**: 20
- **Actors**: 6
- **Started**: 2026-05-18T21:57:07.689616+00:00
- **Ended**: 2026-05-18T21:57:18.860593+00:00

## Per-actor signal averages

| Actor | Turns | upvote_likelihood | would_star | would_homelab_it |
|---|---|---|---|---|
| docker_hoarder | 4 | — | — | — |
| agpl_purist | 4 | — | — | — |
| proxmox_cluster_builder | 3 | — | — | — |
| homelab_newbie | 3 | — | — | — |
| gpu_tinkerer | 3 | — | — | — |
| privacy_maximalist | 3 | — | — | — |

## Trigger

> A new post hit r/selfhosted (and got cross-posted to r/LocalLLaMA):

Title: "exo — Multi-agent simulation engine that scans your hardware
+ services first, generates a config tailored to YOUR machine.
Local-first, Apache 2.0."

Body (from the poster): "Tired of LLM agent frameworks that assume
you'll wire your own everything. Built a thing that probes localhost
for Ollama / Qdrant / Neo4j / Postgres / Claude OAuth / Ollama Cloud,
then writes a docker-compose + YAML config that uses what you have.
Optional databases are profile-gated — `docker compose up` starts
just the runner; `docker compose --profile graph up` adds Neo4j only
when you need it. Sales-call rehearsal example + Mirofish-recreate
example in the repo with full transcripts. Apache 2.0."

You clicked through. You read the README, the WHY, and the Quickstart.
You scanned the example transcript. Now you're commenting on Reddit.


## Full transcript

See `transcript.jsonl`. Each line is one turn.