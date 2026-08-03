# Configuration reference

Settings are loaded from `.env` through Pydantic. Never commit `.env`.

| Variable | Purpose | Production guidance |
|---|---|---|
| `APP_NAME` | OpenAPI/service name | Human-readable value. |
| `APP_BASE_URL` | Public application URL | Use the HTTPS deployment URL. |
| `ADMIN_API_KEY` | Protect administrative APIs | Use a long random secret. |
| `DATABASE_URL` | SQLAlchemy database URL | Use managed PostgreSQL. |
| `META_ACCESS_TOKEN` | Authenticate Graph API | Permanent system-user token. |
| `META_PHONE_NUMBER_ID` | Sending phone-number resource | Copy from WhatsApp setup. |
| `META_WABA_ID` | WhatsApp Business Account ID | Keep for account operations. |
| `META_WEBHOOK_VERIFY_TOKEN` | GET challenge shared secret | Long random value. |
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

Restart the process after changing `.env`; settings are cached per process.
