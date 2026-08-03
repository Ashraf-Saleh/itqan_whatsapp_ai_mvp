# Architecture and module guide

## Request flow

Inbound messages arrive at `POST /webhooks/meta/whatsapp`. The application
verifies the Meta signature, ignores duplicate webhook deliveries, creates or
loads the contact, stores the inbound message, calls the Gemini agent, and
sends the resulting text through Cloud API. Template outreach follows the
opposite direction: an authenticated administrator submits recipients, the
application checks opt-out state, sends the approved template, and stores the
Meta message ID. Later status webhooks are correlated through that ID.

## Modules

### `app.config`

Defines the environment-backed `Settings` model. `get_settings()` caches one
instance so all modules share the same runtime values. String environment
values are sanitized and missing integration credentials produce warnings.

### `app.database`

Creates the SQLAlchemy engine and session factory. SQLite receives its required
thread option; other database URLs use normal SQLAlchemy behavior. `get_db()`
provides one session per FastAPI request.

### `app.models`

Contains three ORM models. `Contact` is the CRM lead, `Message` is the event and
conversation log, and `Unit` is searchable property inventory. Messages belong
to contacts and are deleted with their parent contact.

### `app.schemas`

Validates HTTP request bodies. Recipient names cannot be empty, bulk requests
contain 1–100 recipients, and numeric unit values cannot be negative.

### `app.seed`

Synchronizes `data/units.json` into the database at startup. Unit `code` is the
stable identifier: existing records are updated and new records are inserted.

### `app.agent`

Implements deterministic compliance handling before invoking Gemini. It loads
`system_message.md`, supplies current time context, and exposes inventory, CRM,
handoff, status, and call-booking tools. Conversation history is limited to the
most recent 40 messages. `STOP` and `START` are processed without an LLM.

### `app.messaging.meta`

Builds Cloud API text/template payloads, normalizes phone numbers, submits HTTP
requests, and raises a consistent `MetaAPIError` for configuration or Graph API
errors. It contains no database or business logic.

### `app.main`

Creates the FastAPI application and owns HTTP orchestration: startup, webhook
verification, event extraction, template outreach, simulator, lead APIs,
inventory creation, and dashboard delivery.

### `app.dashboard.html`

A dependency-free administrative page for bulk template outreach, local chat
simulation, and lead-list inspection. It is suitable for development; a
production dashboard should add user authentication, CSRF controls, pagination,
auditing, and role-based access.

## Data and state

SQLite is the MVP default at `data/real_estate_agent.db`. Raw debug webhook
payloads are held only in a five-entry in-memory ring buffer and disappear on
restart. Conversation and status records are durable. Inventory source data is
`data/units.json`; restarting synchronizes it into the database.

## Known scaling boundaries

Inbound AI processing and bulk template sends currently happen inside HTTP
requests. Production scale should move both to a durable queue, acknowledge
webhooks quickly, add idempotency for campaign recipients, and implement
bounded retries with Meta error classification.
