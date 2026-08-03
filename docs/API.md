# API reference

Interactive OpenAPI documentation is available at `/docs`. Administrative
routes require `X-API-Key: <ADMIN_API_KEY>`.

## Public and Meta routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/` | Serve the local dashboard. |
| GET | `/health` | Return service/provider configuration state. |
| GET | `/webhooks/meta/whatsapp` | Answer Meta's verification challenge. |
| POST | `/webhooks/meta/whatsapp` | Receive signed messages and status events. |

## Administrative routes

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/debug/last-payload` | Inspect up to five recent in-memory webhooks. |
| POST | `/api/outreach` | Send the approved template to one named contact. |
| POST | `/api/outreach/bulk` | Send it to 1–100 named contacts. |
| POST | `/api/test-text` | Send diagnostic free-form text inside an open window. |
| POST | `/api/simulator/message` | Run a local inbound message through the agent. |
| GET | `/api/leads` | List CRM leads. |
| GET | `/api/leads/{contact_id}` | Return a lead and conversation/events. |
| POST | `/api/units` | Create an inventory unit. |

`POST /api/test-text` accepts `{"phone":"...","body":"..."}`. It must not
be used to initiate a conversation outside the customer-service window.

## Outreach examples

```bash
curl -X POST http://localhost:8000/api/outreach \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me-now' \
  -d '{"phone":"+201000000000","name":"Ahmed"}'
```

```bash
curl -X POST http://localhost:8000/api/outreach/bulk \
  -H 'Content-Type: application/json' \
  -H 'X-API-Key: change-me-now' \
  -d '{"recipients":[{"phone":"+201000000000","name":"Ahmed"}]}'
```

An accepted response means Meta accepted the API request; delivery is reported
later by webhook. Invalid input returns 422, opted-out contacts return 409 for a
single send, missing/invalid admin credentials return 401, and Meta failures
return 502 for a single send or per-recipient failure details for bulk sends.
