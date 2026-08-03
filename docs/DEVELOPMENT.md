# Development and testing

## Local environment

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Run tests with:

```bash
python -m pytest -q
```

## Inventory

Edit `data/units.json` using UTF-8 JSON. Every item requires a stable unique
`code`. On startup, records with existing codes are updated and new codes are
inserted. Removing an item from JSON does not delete its database row; set
`active` to `false` to exclude it from search.

## Agent behavior

Conversation policy lives in `system_message.md`. Code owns deterministic
controls such as STOP/START, persistence, date parsing, and tool behavior.
Prompt changes should be tested against Egyptian Arabic, English, and
Franco-Arabic inputs and against all escalation triggers.

## Test strategy

Unit tests cover phone normalization, inventory ranking, contact updates, call
windows, opt-out behavior, webhook parsing/signatures/statuses, and exact Meta
payload construction. Integration testing should use Meta test recipients and a
separate WABA before production deployment.

## Safe change workflow

1. Update schema/config documentation with behavioral changes.
2. Add a focused regression test.
3. Run `python -m pytest -q`.
4. Exercise the local simulator.
5. For Meta changes, send only to an opted-in internal test recipient.
6. Confirm webhook delivery and failure events before deployment.

## Deployment notes

The Docker image runs Uvicorn on port 8000 and mounts `./data` through Compose.
For multiple replicas, replace SQLite and the in-memory debug buffer. Run only
one schema migration process and use a durable worker queue for webhook/AI jobs.
