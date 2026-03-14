# OnboardAI

Hackathon MVP for `PS-03: Autonomous Developer Onboarding Agent`.

The canonical onboarding dataset for this repo lives in [`datset/`](/Users/admin/side%20job%20code/sryus/datset).

Core runtime code:
- [`src/onboardai/app.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/app.py)
- [`src/onboardai/graph.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/graph.py)
- [`src/onboardai/content/parser.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/content/parser.py)
- [`src/onboardai/adapters/vector_store.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/vector_store.py)
- [`src/onboardai/adapters/browser.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/browser.py)
- [`src/onboardai/adapters/e2b.py`](/Users/admin/side%20job%20code/sryus/src/onboardai/adapters/e2b.py)

Quick start:

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e .
cp .env.example .env
PYTHONPATH=src python -m onboardai.doctor
PYTHONPATH=src python -m onboardai.app
```

Optional local infra:

```bash
docker compose up -d qdrant
playwright install chromium
```

More detailed project notes are in [`datset/README.md`](/Users/admin/side%20job%20code/sryus/datset/README.md).
