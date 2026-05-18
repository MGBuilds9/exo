# Why exo exists

## The gap

You can describe what you want in plain English:
> "I want to simulate the conversation my sales team is about to have with three stakeholders next week, so I know what objections will come up before I'm in the room."
>
> "I want to simulate the public reaction to this press release with 50 personas of different demographics, so I know what fires to put out before publishing."
>
> "I want to simulate a construction-site contract dispute between the project manager, the estimator, the foreman, and the executive, so I know whose perspective I'm missing."

These all require the same thing: **a multi-agent system where each agent has a persona, a memory, and a position, and they interact under a scenario you define.**

The infrastructure exists. The libraries exist. CAMEL-AI exists. OASIS exists. MiroFish-Offline exists. Yet none of it answers the question *"how do I, today, in 30 minutes, stand up a simulation for my specific scenario without becoming a researcher first?"*

## What's wrong with the existing options

| Option | What's missing |
|---|---|
| Roll your own with LangChain + LLM calls | No memory architecture. No conversation harness. Three months of work before your first transcript. |
| LangGraph | Code-first. Assumes you've already designed the architecture. Designed for product agents, not simulations. |
| CrewAI | Multi-agent, but no opinion on memory tier. No "stand this up for my domain" path. |
| CAMEL-AI / OASIS | The actual engine — but no opinionated bundle, no template library, no "edit one YAML file" path. |
| MiroFish-Offline | Excellent reference implementation, but hardcoded for social-media reaction modeling. Re-purposing it for "sales conversation" requires reading 8,000 lines of Python. |

## What exo does

One thing: **collapse the gap between "I want a simulation of X" and "I have a transcript of X."**

The opinionated bundle is:
1. **Memory architecture**: Qdrant + Neo4j + Postgres in a single `docker compose up`. The canonical hybrid pattern. Pick which tiers your sim needs in YAML; the rest stay idle.
2. **LLM router**: Claude OAuth for frontier agents, Ollama Cloud for cloud OSS, local Ollama for cost-free agents. Each actor picks their own model in YAML.
3. **Architect CLI**: 12 questions. Outputs a complete `domain.yaml` + `scenario.yaml`. No PhD required.
4. **Template library**: Pre-built simulations for the most common cases (social-media, sales, wedding-coordination, healthcare-triage, construction-stakeholder, incident-response). `cp -r` and edit.
5. **YAML-first config**: Every aspect of a sim is declarative. Version it. Diff it. Hand it to a teammate.

Everything else — the runtime, the agent loop, the embeddings — is delegated to libraries that already do their jobs well.

## What exo is NOT

- **Not a chatbot framework.** This is for simulating populations of agents, not deploying one assistant.
- **Not a LangChain killer.** LangChain is for production agents that serve users. exo is for *rehearsal* — simulating what would happen so you can prepare.
- **Not vendor lock-in.** AGPL-3.0. Runs on your laptop. Runs on your homelab. Plug whichever LLM you want. Take your YAML config and run it elsewhere if you outgrow the bundle.
- **Not magic.** Multi-agent simulation produces plausible synthesis, not ground truth. Treat transcripts as hypotheses to stress-test in reality, not as predictions to act on directly.

## Who exo is for

If you've ever wished you could ask "what would happen if..." and get a transcript instead of a guess, exo is for you.

If you're three days from a high-stakes meeting and you want to rehearse against simulated stakeholders before walking in, exo is for you.

If you're a researcher modeling social dynamics, organizational behavior, or market reactions and you don't want to rebuild the harness from scratch, exo is for you.

If you're a homelab self-hoster who refuses to send your prompts to OpenAI, exo is for you.

If you build personal AI tools and want the substrate that the next ten of them can stand on, exo is for you.

## The thesis

**Personal AI infrastructure should be bundled, opinionated, and yours.** Not a SaaS that disappears when the company pivots. Not a hyperscaler tab that breaks every 6 months when the model deprecates. Not a 14-step Substack tutorial that's six versions out of date by the time you reach step 8.

`docker compose up`. Edit a YAML file. Get a transcript. Yours forever.
