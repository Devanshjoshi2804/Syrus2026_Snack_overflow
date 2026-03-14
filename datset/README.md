# OnboardAI

Hackathon MVP for `PS-03: Autonomous Developer Onboarding Agent`.

This repo now contains a runnable local-first implementation that:
- matches an employee persona from the provided markdown dataset
- builds a personalized onboarding checklist
- answers onboarding questions with grounded retrieval over the dataset
- completes deterministic terminal tasks with a mock or E2B sandbox
- supports optional Playwright browser actions with no paid model API
- generates structured HTML and JSON completion reports for HR

## Stack

- `Python 3.11`
- `Chainlit`
- `LangGraph`
- `Qdrant` or embedded/in-memory vector store
- `sentence-transformers` or hash embeddings
- optional `Ollama`
- optional `Playwright`
- optional `E2B`
- Docker Compose for local Qdrant

## Zero-Key Default

The default path is intentionally local-first.

- No Claude or Anthropic API key is required
- `ONBOARDAI_MODE=dev_mock` works with mock sandbox + mock browser
- `ONBOARDAI_LLM_BACKEND=heuristic` avoids all hosted model usage
- You can switch on Ollama or Playwright later without changing the core flow

## Repo Layout

Canonical dataset location:
- [`datset/`](/Users/admin/side%20job%20code/sryus/datset)

- [src/onboardai/app.py](/Users/admin/side%20job%20code/sryus/src/onboardai/app.py): Chainlit entrypoint and CLI demo
- [src/onboardai/graph.py](/Users/admin/side%20job%20code/sryus/src/onboardai/graph.py): onboarding engine and flow routing
- [src/onboardai/content/parser.py](/Users/admin/side%20job%20code/sryus/src/onboardai/content/parser.py): dataset parsing
- [src/onboardai/adapters/vector_store.py](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/vector_store.py): memory and Qdrant backends
- [src/onboardai/adapters/browser.py](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/browser.py): mock and Playwright browser backends
- [src/onboardai/adapters/e2b.py](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/e2b.py): mock and E2B sandbox backends
- [src/onboardai/email/generator.py](/Users/admin/side%20job%20code/sryus/src/onboardai/email/generator.py): HR report generation
- [compose.yaml](/Users/admin/side%20job%20code/sryus/compose.yaml): local Qdrant service
- [datset/setup_guides.md](/Users/admin/side%20job%20code/sryus/datset/setup_guides.md), [datset/starter_tickets.md](/Users/admin/side%20job%20code/sryus/datset/starter_tickets.md), [datset/guidelines.md](/Users/admin/side%20job%20code/sryus/datset/guidelines.md): canonical dataset inputs

## Quick Start

1. Create a Python 3.11 virtualenv:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
```

2. Copy environment defaults:

```bash
cp .env.example .env
```

3. Run the local health check:

```bash
PYTHONPATH=src python -m onboardai.doctor
```

4. Run the CLI smoke demo:

```bash
PYTHONPATH=src python -m onboardai.app
```

5. Run tests:

```bash
PYTHONPATH=src pytest
```

## Docker Qdrant

Start Qdrant locally:

```bash
docker compose up -d qdrant
```

Then set:

```bash
ONBOARDAI_VECTOR_BACKEND=remote_qdrant
ONBOARDAI_QDRANT_URL=http://localhost:6333
```

The app will fall back to in-memory storage if Qdrant is unreachable.

## Playwright Browser Mode

Install the Python package and browser runtime:

```bash
pip install playwright
playwright install chromium
```

Enable it:

```bash
ONBOARDAI_BROWSER_BACKEND=playwright
ONBOARDAI_BROWSER_HEADLESS=true
```

Browser tasks remain optional. If Playwright is unavailable, the app falls back to mock browser behavior.

Set your real demo endpoints in `.env` so the browser flow points at valid pages:

```bash
ONBOARDAI_GITHUB_ORG_URL=https://github.com/<your-demo-org>
ONBOARDAI_SLACK_WORKSPACE_URL=https://<your-demo-workspace>.slack.com
ONBOARDAI_JIRA_URL=https://<your-demo-site>.atlassian.net
```

## Ollama Mode

If you want local model phrasing on top of deterministic retrieval:

```bash
ollama pull qwen2.5-coder:7b
```

Then set:

```bash
ONBOARDAI_LLM_BACKEND=ollama
OLLAMA_MODEL=qwen2.5-coder:7b
```

The system still stays grounded in retrieved dataset content.

## Chainlit

Once dependencies are installed:

```bash
chainlit run src/onboardai/app.py
```

Sample intro:

```text
Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.
```

## Current Status

Implemented:
- persona extraction and deterministic persona scoring
- adaptive checklist planning
- retrieval over the onboarding knowledge base
- deterministic terminal automation
- mock/E2B sandbox abstraction
- mock/Playwright browser abstraction
- HTML + JSON HR completion reports
- dashboard element for live verification state
- test suite for the core MVP flow

Not implemented yet:
- full browser task automation flows beyond open-and-capture
- multi-day delay detection and weekly status emails
- end-to-end live Slack/Jira/GitHub mutations
- production deployment packaging
