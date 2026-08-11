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
