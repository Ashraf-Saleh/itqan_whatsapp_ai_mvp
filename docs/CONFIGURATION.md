# Configuration reference

Settings are loaded from `.env` through Pydantic. Never commit `.env`.

| Variable | Purpose | Production guidance |
|---|---|---|
| `APP_NAME` | OpenAPI/service name | Human-readable value. |
| `APP_BASE_URL` | Public application URL | Use the HTTPS deployment URL. |
| `ADMIN_API_KEY` | Protect administrative APIs | Use a long random secret. |
| `DATABASE_URL` | SQLAlchemy database URL | Use managed PostgreSQL. |
| `META_APP_SECRET` | Verify webhook signatures | Required when validation is on. |
| `META_VALIDATE_SIGNATURE` | Enforce Meta signatures | Set `true` in production. |
| `META_GRAPH_API_VERSION` | Graph API path version | Test before upgrading. |
| `META_TEST_TEMPLATE_NAME` | Exact approved template name | Current: `itqan_lead_outreach`. |
| `META_TEST_TEMPLATE_LANGUAGE` | Exact language code | Current: `ar`. |
| `META_TEMPLATE_PARAMETER_COUNT` | Body variable count | Current contract: `1`. |
| `GEMINI_API_KEY` | Authenticate Gemini | Store in a secret manager. |
| `GEMINI_MODEL` | Gemini model identifier | Validate behavior on changes. |
| `QWEN_URL` | Base URL of the OpenAI-compatible Qwen server | Either the bare host or a URL ending in `/v1` both work — `/v1` is appended automatically if missing. |
| `QWEN_MODEL` | Model name to send in each request | Must match what the server expects. |
| `QWEN_API_KEY` | Bearer token for the Qwen server | Leave blank if the server doesn't enforce auth. |
| `HUMAN_SALES_NAME` | Handoff display/assignment | Use a real queue/team label. |
| `HUMAN_SALES_PHONE` | Sales contact configuration | Not exposed unless implemented. |
| `COMPANY_NAME` | Replaces `[Agency Name]` in prompt | Current: ITQAN Real Estate. |

Restart the process after changing `.env`; these settings are cached per process.

## Meta credentials (`meta_secrets.py`)

The access token, phone number ID, WABA ID, and webhook verify token live
outside `.env`, in a `meta_secrets.py` file at the repo root (never
committed — see `meta_secrets.example.py` for the template). It is loaded by
`app/meta_credentials.py`, which is a different file: that module holds the
loading/validation logic, while `meta_secrets.py` holds the actual values:

```python
ACCESS_TOKEN = "..."
PHONE_NUMBER_ID = "..."
WABA_ID = "..."
WEBHOOK_VERIFY_TOKEN = "..."
```

| Field | Purpose | Production guidance |
|---|---|---|
| `ACCESS_TOKEN` | Authenticate Graph API | Permanent system-user token. |
| `PHONE_NUMBER_ID` | Sending phone-number resource | Copy from WhatsApp setup. |
| `WABA_ID` | WhatsApp Business Account ID | Keep for account operations. |
| `WEBHOOK_VERIFY_TOKEN` | GET challenge shared secret | Long random value. |

Unlike `.env`, this file is **hot-reloaded**: the app checks its modification
time on every request and re-executes it when it changes (via
`runpy.run_path`, not a normal `import`, so Python's module cache never masks
an edit), so rotating a token only requires editing `meta_secrets.py` on
disk — no restart needed. If the file is missing or invalid, requests that
need Meta credentials fail fast with a clear error instead of silently using
stale or empty values.

Because this file is executed as Python (not parsed as inert data like
JSON), only edit it yourself or via trusted deploy tooling — anyone who can
write to it can run arbitrary code in the app process, the same trust level
already required for `.env`.

## Switching the active LLM model (Gemini / Qwen)

Unlike the settings above, *which* model handles conversations is not read
from `.env` — it's a single value persisted in the database (`AppSetting`
table, `app/models.py`) and switchable at runtime with no restart:

- `GET /api/settings/active-model` and `POST /api/settings/active-model`
  (both admin-protected, `X-API-Key`) read and set it; the dashboard's model
  selector at the top of the page calls these.
- Every subsequent inbound message (sandbox and real) uses whichever
  provider is currently selected — `process_message` re-reads it on every
  call, so a switch takes effect on the very next message.
- Both providers receive the **identical system prompt** (`system_message.md`
  via `build_system_instruction()`) and the **identical set of tools**
  (`search_units`, `save_client`, `escalate_to_agent`, `book_call`,
  `update_client_status`) — only how tool-calling is wired up differs:
  - Gemini's SDK derives tool schemas automatically from each tool's Python
    signature and docstring, and runs the "call tool → feed back result →
    re-prompt" loop internally.
  - Qwen goes through a generic OpenAI-compatible `/v1/chat/completions`
    endpoint, which doesn't do either of those for us. `app/agent.py`
    hand-writes the tool schemas as `QWEN_TOOL_SCHEMAS` and runs that loop
    manually in `call_qwen()`. **`QWEN_TOOL_SCHEMAS` is not derived from the
    tool docstrings — if you change a tool's parameters, update both.**
