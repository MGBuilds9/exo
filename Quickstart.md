# Quickstart

Five minutes from clone to first transcript.

## Fastest path (zero databases, fully local — no cloud accounts needed)

For simple multi-actor chat sims, you don't need Docker, Qdrant, Neo4j,
or Postgres. The DBs are optional and only matter when your sim declares
a memory tier. The LLM can be a local Ollama model.

```bash
# Prereqs: Python 3.11+, Ollama running locally
ollama pull qwen2.5:14b
ollama serve &

# Clone and run
git clone https://github.com/MGBuilds9/exo.git
cd exo
pip install -r requirements.txt
export LOCAL_OLLAMA_BASE_URL=http://localhost:11434/v1

# Edit the template to use local-ollama instead of ollama-cloud:
sed -i 's|ollama-cloud/qwen3-coder:480b|local-ollama/qwen2.5:14b|g' \
    templates/sales-pipeline/domain.yaml

./exo run templates/sales-pipeline/domain.yaml
```

Four commands. No Docker. No cloud account. No API key. Your prompts
and personas never leave your machine.

## Full path (with memory tiers)

For sims that use vector retrieval / graph relationships / structured records,
spin up the database stack:

## 0. Prereqs

- Docker + Docker Compose
- Python 3.11+ (for the CLI; the runner runs in Docker)
- An LLM endpoint. Pick one:
  - **Ollama Cloud** (easiest — frontier OSS models via API): get key at https://ollama.com
  - **Local Ollama** (free; needs ≥16GB RAM): `ollama pull qwen2.5:14b`
  - **Claude OAuth** (frontier): requires Claude Code installed (v0.2+)

## 1. Clone

```bash
git clone https://github.com/MGBuilds9/exo.git
cd exo
cp .env.example .env
# Edit .env — set ONE of OLLAMA_CLOUD_API_KEY, LOCAL_OLLAMA_BASE_URL, or leave Claude OAuth defaults
```

## 2. Start the stack

```bash
docker compose up -d
# Wait ~30s for Neo4j health check
curl -s http://localhost:5050/health
# → {"service": "exo-runner", "status": "ok"}
```

## 3. Run an existing template

```bash
pip install -r requirements.txt
./exo run templates/sales-pipeline/domain.yaml
```

You'll see a 20-turn transcript in real-time, with sentiment + trust +
deal_momentum signals tracked per actor per turn. Total run time:
~2 minutes against Ollama Cloud.

## 4. Or design your own

```bash
./exo architect
# 12 questions → writes ./<your-name>/domain.yaml + scenario.yaml
cd <your-name>
../exo run domain.yaml
```

## 5. Inspect

```bash
./exo report sims/<your-sim>/run/
# Or just open the transcript.jsonl and the summary.md
```

## Common edits

**Change which LLM each actor uses** — edit `domain.yaml`:

```yaml
actors:
  - id: my_agent
    persona: ...
    model: ollama-cloud/qwen3-coder:480b   # ← change this
```

Supported: `claude-oauth`, `ollama-cloud/<model>`, `local-ollama/<model>`.

**Change the trigger event** — edit `scenario.yaml` `trigger:` field.

**Add a signal** — edit `scenario.yaml` `signals:` list. Actors will emit
values for any signal you name.

## When something breaks

Most failures are LLM connectivity. Check:

```bash
# Ollama Cloud?
curl -H "Authorization: Bearer $OLLAMA_CLOUD_API_KEY" https://ollama.com/api/tags

# Local Ollama?
curl http://localhost:11434/v1/models

# Claude OAuth?
which claude && claude --version
```

If the LLM is reachable but actors produce gibberish, drop `temperature`
in `domain.yaml` to 0.5 and try again.
