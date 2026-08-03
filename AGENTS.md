# AGENTS.md

## Project overview

ITQAN is a FastAPI MVP that connects Meta WhatsApp Cloud API to a Gemini-powered Egyptian-Arabic real-estate assistant. It receives and authenticates webhooks, persists CRM and conversation data, searches property inventory, books calls, and hands leads to sales.

Read `README.md` first. Detailed references live in `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/CONFIGURATION.md`, `docs/DEVELOPMENT.md`, and `docs/META_WHATSAPP.md`.

## Development commands

- Install dependencies: `python -m pip install -r requirements.txt`
- Run locally: `python -m uvicorn app.main:app --reload`
- Run all tests: `python -m pytest -q`
- Windows shortcut: `run_windows.bat`
- Linux shortcut: `./run_linux.sh`

Use the browser simulator at `http://localhost:8000` for local message-flow checks. Meta credentials are not required for the simulator.

## Code map

- `app/main.py`: FastAPI routes and HTTP orchestration.
- `app/agent.py`: deterministic compliance controls, Gemini integration, and agent tools.
- `app/messaging/meta.py`: phone normalization and Meta Graph API payloads/requests; no business or database logic belongs here.
- `app/models.py`, `app/schemas.py`, `app/database.py`: persistence and validation.
- `app/seed.py` and `data/units.json`: inventory synchronization.
- `system_message.md`: conversational policy and agent behavior.
- `app/dashboard.html`: dependency-free development dashboard and simulator.
- `tests/`: pytest regression suite.

## Change guidelines

- Preserve the existing separation between HTTP orchestration, business/compliance logic, persistence, and Meta transport.
- Keep `STOP`, `START`, signature verification, opt-out enforcement, deduplication, and other compliance-critical behavior deterministic rather than prompt-only.
- Add or update focused tests for every behavioral change. Run `python -m pytest -q` before handing off.
- Update the relevant file under `docs/` when APIs, configuration, schemas, deployment, or behavior changes.
- For prompt changes, test Egyptian Arabic, English, and Franco-Arabic inputs as well as escalation and handoff triggers.
- Keep inventory codes stable and unique. Deactivate removed inventory with `"active": false`; deleting it from JSON does not delete the database record.
- Use timezone-aware dates and retain the project's Egypt-focused call-booking behavior.
- Keep webhook handling idempotent and preserve Meta message-ID/status correlation.

## Safety and repository hygiene

- Never commit `.env`, access tokens, app secrets, customer phone numbers, consent records, database contents, or logs.
- Treat `.env` as private. Add new variables to `.env.example` with safe placeholders and document them in `docs/CONFIGURATION.md`.
- Do not send real WhatsApp messages or bulk outreach during tests. Use mocks, the local simulator, or an explicitly authorized opted-in test recipient.
- Do not weaken signature validation, admin authentication, opt-out checks, or consent requirements.
- Avoid editing generated/runtime artifacts such as `data/real_estate_agent.db`, `logs/`, caches, and bytecode.
- Preserve unrelated user changes in a dirty working tree; do not reset or overwrite them.

## Completion checklist

1. Implement the smallest coherent change.
2. Add regression coverage.
3. Run `python -m pytest -q`.
4. Update affected documentation and `.env.example` when applicable.
5. Summarize changed files, verification performed, and any remaining production or compliance risk.
