# ITQAN WhatsApp Real Estate AI MVP

A small, testable FastAPI MVP for Meta WhatsApp Cloud API. A Gemini-powered agent (driven by [`system_message.md`](system_message.md)) chats with real-estate leads in Egyptian Arabic, searches the unit inventory, saves client info, books calls, and hands qualified clients to a human sales team.

## Fastest local test (no Meta required)

### Windows
Double-click `run_windows.bat`, then open `http://localhost:8000`.

### Linux/macOS
```bash
./run_linux.sh
```

Set `GEMINI_API_KEY` in `.env` (see `.env.example`) before starting the app, otherwise the agent replies with a fallback "unavailable" message. Use API key `change-me-now` in the dashboard and chat with the simulator like a real client, e.g. "عايز شقة في 6 أكتوبر".

## Agent behavior

The conversational behavior, tone, and tool-usage rules live entirely in [`system_message.md`](system_message.md) — edit that file to change how the agent talks or what it asks for; no code changes needed. The agent (`app/agent.py`) loads it as the Gemini system instruction and exposes these tools, backed by the database:

- `search_units` — ranks the closest matches in the unit inventory (`Unit` table / `data/units.json`).
- `save_client` — saves collected client info onto the `Contact` record.
- `escalate_to_agent` — hands the conversation off to a human sales agent.
- `book_call` — books a call at a confirmed date/time.
- `update_client_status` — updates the client's CRM pipeline status.

`STOP`/`START` opt-out and opt-in are handled in code (not by the LLM) for compliance.

## Docker
```bash
docker compose up --build
```
Open `http://localhost:8000`.

## Meta Cloud API configuration
1. Create a Meta Business app and add WhatsApp.
2. Add your phone as a test recipient.
3. Copy the temporary access token and Phone Number ID to `.env`.
4. Choose `META_WEBHOOK_VERIFY_TOKEN`.
5. Expose port 8000 using ngrok or deploy the app.
6. Configure callback URL: `https://YOUR-DOMAIN/webhooks/meta/whatsapp`.
7. Subscribe to the `messages` webhook field.
8. For the first test keep `META_VALIDATE_SIGNATURE=false`; once the app secret is configured, set it to `true`.
9. Send the approved `hello_world` test template from `/docs` using `POST /api/outreach`.

## Main endpoints
- `/` local simulator and lead dashboard
- `/docs` interactive API documentation
- `/health` health check
- `GET/POST /webhooks/meta/whatsapp` Meta webhook
- `POST /api/outreach` template outreach
- `POST /api/simulator/message` local test
- `GET /api/leads` lead list

## Unit inventory
Edit `data/units.json`, then restart the app. Existing units are updated by `code`.

## Production notes
Before real customer use, replace the temporary token, enable signature validation, use approved templates, record opt-in, configure HTTPS, change the admin key, and migrate SQLite to PostgreSQL.
