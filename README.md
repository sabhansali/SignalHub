# SignalHub

**Evidence-Backed Account Intelligence & Sales Research Platform**

SignalHub is a Mastek-focused portfolio project that turns public account information into traceable intelligence for research, pre-sales, and sales workflows.

## v1 goals

- Account intelligence: organisation/business structure, recent developments, technology signals, buying signals, potential whitespace, and Mastek point of view.
- ICP and account prioritisation with documented scoring logic.
- Competitor and partner intelligence using the same evidence model.
- Event intelligence and account mapping.
- HubSpot engagement context.
- Detailed pre-sales brief and concise sales brief.
- Research requests, small-project workflow, human review, and approval.
- Automation: scheduled refresh, change detection, alerts, and weekly change digests.
- Evidence validation so unsupported claims are blocked from approval.

## Stack

React + FastAPI + PostgreSQL + LanceDB + SentenceTransformers + Python + Docker + Pytest + GitHub Actions.

## Development

1. Copy `.env.example` to `.env`.
2. For the quickest local start, leave the default SQLite URL in place.
3. For normal development, start PostgreSQL with `docker compose up -d` and use the PostgreSQL `DATABASE_URL` from `.env.example`.
4. Create the schema with `python scripts/init_db.py`.
5. Run the API with `uvicorn app.main:app --reload` from the repository root after installing the project package.

See `docs/architecture.md` for the frozen v1 architecture.
