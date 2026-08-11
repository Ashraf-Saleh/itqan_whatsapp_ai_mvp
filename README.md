# ITQAN WhatsApp Real Estate AI MVP

ITQAN is a FastAPI application that connects Meta WhatsApp Cloud API to a
Gemini-powered Egyptian-Arabic real-estate assistant. It receives leads,
recommends inventory, stores qualification data, books calls, and hands
conversations to the sales team.

## Capabilities

- Receive and authenticate Meta WhatsApp webhooks.
- Understand text, quick-reply buttons, and interactive selections.
- Start conversations with an approved Arabic marketing template.
- Send bulk outreach to up to 100 named recipients per request.
- Respect application-level `STOP` and `START` commands.
- Search and rank the local property inventory.
- Save lead requirements, conversation history, and delivery events.
- Escalate to sales or book a confirmed call.
- Test locally with a browser simulator without Meta credentials.

## Architecture

```text
Meta WhatsApp -> FastAPI webhook -> compliance checks -> Gemini agent
                                      |                  |
                                      v                  v
                                SQLite CRM         inventory/tools
                                      ^
Dashboard/API -> approved template --|
```

Detailed documentation:

- [Architecture and module guide](docs/ARCHITECTURE.md)
- [Meta template and webhook setup](docs/META_WHATSAPP.md)
- [API reference](docs/API.md)
- [Configuration reference](docs/CONFIGURATION.md)
- [Development and testing](docs/DEVELOPMENT.md)

## Quick start

1. Create a virtual environment and install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env`, set `GEMINI_API_KEY`, and change
   `ADMIN_API_KEY`.

3. Start the service:

   ```bash
   ./run_linux.sh
   ```

4. Open `http://localhost:8000` for the simulator or
   `http://localhost:8000/docs` for OpenAPI.

Windows users can activate the environment and run `run_windows.bat`.

Every request, webhook payload, and error is printed to the console and also
persisted to `logs/app.log` (rotated at 5 MB, 5 backups kept), so a live
`tail`/`Get-Content -Wait` and a permanent record are always both available.

## Deploy to Render

`render.yaml` defines a Docker web service plus a managed Postgres database as
a Render Blueprint.

1. Push this repository to GitHub/GitLab, then in the Render dashboard choose
   **New > Blueprint** and point it at the repo. Render reads `render.yaml`
   and provisions both resources.
2. Fill in the `sync: false` environment variables in the web service's
   **Environment** tab: `ADMIN_API_KEY`, `META_APP_SECRET`, `GEMINI_API_KEY`.
   `DATABASE_URL` is wired automatically from the provisioned Postgres
   instance.
3. Add `meta_secrets.py` (`ACCESS_TOKEN`, `PHONE_NUMBER_ID`, `WABA_ID`,
   `WEBHOOK_VERIFY_TOKEN`) as a Render **Secret File** mounted at
   `/app/meta_secrets.py`, using `meta_secrets.example.py` as the
   template — see [docs/CONFIGURATION.md](docs/CONFIGURATION.md). This file
   is hot-reloaded, so rotating a token later only means editing the secret
   file's content in the Render dashboard, not redeploying.
4. Deploy. Once live, note the service URL
   (`https://<service-name>.onrender.com`).
5. In the Meta App Dashboard, set the webhook callback URL to
   `https://<service-name>.onrender.com/webhooks/meta/whatsapp` and the verify
   token to the same value as `WEBHOOK_VERIFY_TOKEN` in
   `meta_secrets.py`.
6. **Subscribe the app to the WABA** — setting the callback URL alone is not
   enough. Run (using the `WABA_ID` / `ACCESS_TOKEN` values from
   `meta_secrets.py`):

   ```bash
   curl -X POST "https://graph.facebook.com/v26.0/<waba_id>/subscribed_apps" \
     -H "Authorization: Bearer <access_token>"
   ```

   Verify with a GET on the same URL — the response's `data` array must
   include your app, not just Meta's own "WA DevX Webhook Events" app. Without
   this step, the Dashboard's "Test" button will appear to work (it injects
   payloads directly) while real messages from customers never arrive. See
   [docs/META_WHATSAPP.md](docs/META_WHATSAPP.md) for the full webhook setup
   sequence.
7. The Blueprint defaults to Render's **free** plan for both the web service
   and the database. The free web service spins down after ~15 minutes idle
   and cold-starts (30-60s) on the next request, which can drop or delay real
   webhook deliveries; the free Postgres instance also expires after about 30
   days. Upgrade both to a paid plan (`starter` or higher) before relying on
   this for real customer traffic.

## Current Meta template contract

The application is configured for:

- Name: `itqan_lead_outreach`
- Language: `ar`
- Category: Marketing
- Body variables: one variable, `{{1}}`, containing the recipient name

The Meta screenshot dated August 3, 2026 shows the template **In review** and
its Arabic preview rendered as question marks. Do not send production outreach
until the template preview displays real Arabic and Meta marks it Active. See
[the remediation procedure](docs/META_WHATSAPP.md#repair-the-corrupted-arabic-template).

## Production checklist

- Obtain documented WhatsApp opt-in before outreach.
- Repair and approve the Arabic marketing template.
- Use a permanent system-user token and protect all secrets, including
  `meta_secrets.py` (never commit it — see
  [docs/CONFIGURATION.md](docs/CONFIGURATION.md)).
- Set `META_VALIDATE_SIGNATURE=true` and configure `META_APP_SECRET`.
- Deploy behind HTTPS and replace the default admin key.
- Move from SQLite to managed PostgreSQL (`render.yaml` provisions this).
- Upgrade the Render web service and database off the free plan (see
  "Deploy to Render") so idle spin-down cannot drop real webhook traffic.
- Add a task queue for large campaigns and Meta retry/rate-limit handling.
- Establish retention, access-control, monitoring, and incident procedures.

## Important compliance boundary

The code blocks contacts who opted out in this application. It does not prove
that a contact originally opted in. The business must maintain consent records
and send marketing outreach only to eligible recipients under Meta policy and
applicable law.
