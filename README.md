# AI Model Selection & Governance Agent

Backend for TDRA Challenge #11 (problems R1–R7). A shared, risk-proportionate path from use-case
definition to risk tier, evidence, parallel evaluation, accountable human approval and monitoring,
for four synthetic government departments connected through one registry.

Departments, people, models and providers are synthetic and invented. Test data also includes real published
statistics from Bayanat.ae, the UAE open data portal (aggregate tables, no personal data).

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Foundation: schema, migrations, login, CORS, seed data, registry read API, append-only audit | done |
| 2 | Intake, risk tiering, evidence normalisation, reuse engine, assessment plan | done |
| 3 | Test runner, three evaluation agents in parallel, compliance checklist, critic | done |
| 4 | Reviews in parallel, concerns, decision record, human approval, deployments, scenario runner | done |
| 5 | Lifecycle monitor (triggers, alerts, exit rules, reassessment), incidents, feedback, metrics | done |
| + | Open data: real Bayanat.ae tables, test cases computed from them, update monitoring | done |

## Run locally

Needs Python 3.12 and a local Postgres.

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt
createdb tdra_gov
cp .env.example .env
.venv/bin/alembic upgrade head
.venv/bin/python -m app.seed
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000/docs. To log in: `POST /auth/login` with a seeded email
(list them with `GET /auth/users`), then press **Authorize** and paste the `access_token`.

- Reload the seed data from scratch: `.venv/bin/python -m app.seed --reset`
- Run the tests: `.venv/bin/pytest` (uses its own database, `tdra_gov_test`, rebuilt on every run)
- Run a scenario: `GET /scenarios` lists them; `POST /scenarios/{a..e}/run` runs one up to the point where named
  people must act, and returns who must do what next. See HANDOFF.md for the walk-through.

## Layout

```
render.yaml              Render blueprint (web service + Postgres)
backend/
  app/
    main.py              FastAPI app, CORS
    config.py            settings from environment variables
    catalog.py           shared vocabulary: checks, tiers, evidence fields, triggers
    models.py            database tables
    schemas.py           API response shapes
    security.py          login tokens, current user
    audit.py             audit-row helper
    llm.py               OpenRouter gateway: JSON, validation, retry, logging, mock mode
    services/            tiering, evidence, reuse, planning, compliance rules, test runner, evaluation agents,
                         governance (reviews, decision record, approval), lifecycle (monitor, exit rules), metrics
    routers/             auth, org, intake, models, evidence, assessments, governance, lifecycle, scenarios, registry
    seed/                synthetic data: org, registry history, test sets
  alembic/               migrations (0001 schema and append-only triggers, 0002 plan, 0003 governance and lifecycle, 0004 open data)
  tests/
```

## Deploy

- **Render (backend):** create a Blueprint from `render.yaml`. Set `OPENROUTER_API_KEY` and `CORS_ORIGINS`
  (the Vercel URL) in the dashboard. Migrations and the seed run on every start; the seed does nothing if data exists.
- **Vercel (frontend, later):** point it at the Render URL. Auth is a bearer token in the `Authorization` header.

## Frontend (Almanara)

`frontend/` is the designer's static prototype, unchanged, plus one add-on file, `frontend/js/api.js`, and the one
`<script>` line that loads it. The page opens on its own sample data. The **Sample data** button in the header lets you
pick a seeded person and connect; Overview, Departments, Registry and Monitor then show the backend's records, read-only.
The New use case wizard and its pipeline, the ROI figures and the Monitor's Pause / Re-check buttons are still the
prototype's own simulation and say so.

Run both locally (the backend allows `http://localhost:5173` by default):

```bash
cd backend && .venv/bin/uvicorn app.main:app --port 8000
cd frontend && python3 -m http.server 5173     # then open http://localhost:5173/assurance-with-intro.html
```

The add-on calls `http://localhost:8000` when the page is opened locally and the Render service otherwise;
`?api=https://host` points it somewhere else (remembered), and `?sample=1` keeps the sample data.

**Vercel:** set the project's root directory to `frontend` (no build step; `vercel.json` serves the page at `/`).
Then add the Vercel URL to `CORS_ORIGINS` on the Render service, or set `CORS_ORIGIN_REGEX` to
`https://.*\.vercel\.app`, or the browser will refuse the calls.

## Models under test

Registry models have invented names. `openrouter_id` says which OpenRouter endpoint is called when the model is
tested; set `MODEL_ID_OVERRIDES` to point a registry model at a different one without reseeding.
