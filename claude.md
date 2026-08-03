# Claude Project Instructions

This repository contains the ITQAN WhatsApp Real Estate AI MVP: a FastAPI and SQLAlchemy service connecting Meta WhatsApp Cloud API to a Gemini-powered Egyptian-Arabic real-estate assistant.

## Start here

Read `README.md` and `AGENTS.md` before changing code. Use the detailed documentation under `docs/` for architecture, APIs, configuration, Meta setup, and development workflows.

## Standard workflow

1. Inspect the relevant implementation, tests, and documentation before editing.
2. Make the smallest change that fully addresses the request.
3. Add a focused regression test for behavioral changes.
4. Run `python -m pytest -q`.
5. Update documentation and `.env.example` when configuration or external behavior changes.

Run the app with `python -m uvicorn app.main:app --reload`. The local simulator is available at `http://localhost:8000` and should be preferred over real Meta messaging during development.

## Architecture boundaries

- `app/main.py` owns routes and orchestration.
- `app/agent.py` owns deterministic conversation/compliance controls, Gemini calls, and tools.
- `app/messaging/meta.py` owns Meta payload construction and HTTP transport, without database or business logic.
- `app/models.py`, `app/schemas.py`, and `app/database.py` own persistence and validation.
- `system_message.md` owns conversational policy, but safety and compliance controls must remain enforced in code.

## Non-negotiable safeguards

- Preserve deterministic `STOP`/`START`, opt-out, webhook signature, deduplication, authentication, and consent-related behavior.
- Never expose or commit `.env`, API keys, Meta tokens, app secrets, customer data, databases, or logs.
- Never send production or bulk WhatsApp outreach as part of routine testing.
- Do not claim that application-level opt-out handling proves original marketing consent.
- Preserve Egyptian Arabic and Franco-Arabic behavior when editing prompts or conversation logic.
- Keep inventory `code` values stable and unique; use `active: false` rather than assuming removal from JSON deletes a database row.
- Do not modify runtime artifacts in `data/`, `logs/`, caches, or bytecode unless explicitly requested.

When finished, report the files changed, tests run and their results, plus any unresolved deployment, Meta-policy, security, or compliance concerns.
