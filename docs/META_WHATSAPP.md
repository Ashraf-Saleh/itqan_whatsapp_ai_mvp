# Meta WhatsApp setup and template operations

## Current finding

The WhatsApp Manager screenshot from August 3, 2026 shows:

- `itqan_lead_outreach`
- Arabic
- Marketing category
- Status: In review
- A preview whose Arabic characters appear as question marks

“In review” is not approval. The question marks indicate the submitted content
or the browser input path was corrupted before or during template creation; the
application cannot repair text stored inside WhatsApp Manager.

## Repair the corrupted Arabic template

1. Open WhatsApp Manager and edit `itqan_lead_outreach`. If Meta prevents edits
   while it is in review, create a new template with a new name such as
   `itqan_lead_outreach_v2`.
2. Type or paste the Arabic from a UTF-8 source directly into WhatsApp Manager.
   Do not paste from a legacy ANSI file, a PDF extraction, or software that
   already displays question marks.
3. Keep the category as **Marketing**. This message initiates a sales
   conversation and must not be represented as Utility.
4. Use exactly one body variable and supply an Arabic example for it.
5. Confirm the preview itself shows readable Arabic before submitting.
6. Wait until the status is **Active**, then set the exact approved name in
   `META_TEST_TEMPLATE_NAME`.
7. Send to one opted-in internal test number and confirm sent, delivered, read,
   reply, and opt-out behavior before any campaign.

Suggested body text (review it with the business/compliance owner before use):

```text
أهلاً {{1}}، مع حضرتك فريق إتقان العقارية. عندنا وحدات عقارية ممكن تناسب احتياجات حضرتك. لو حابب تعرف التفاصيل، رد على الرسالة دي. ولو مش حابب تستقبل رسائل مننا، اكتب إلغاء.
```

Example for `{{1}}`: `أحمد`

Do not copy the template from a terminal or file unless it is saved as UTF-8.
The repository files are UTF-8, but Meta's preview remains the final check.

## Cloud API configuration

1. Create a Meta Business app and add WhatsApp.
2. Configure a WhatsApp Business Account and phone number.
3. Use a permanent system-user access token in production.
4. Set the variables described in `CONFIGURATION.md`.
5. Expose an HTTPS callback at `/webhooks/meta/whatsapp` (see the Render
   deployment steps in the root `README.md` for a stable, non-tunnel URL).
6. Subscribe the WhatsApp account to the `messages` webhook field in the App
   Dashboard **and** subscribe the app to the WABA via the Graph API — the
   Dashboard field checkbox alone is not sufficient:

   ```bash
   curl -X POST "https://graph.facebook.com/v26.0/<WABA_ID>/subscribed_apps" \
     -H "Authorization: Bearer <META_ACCESS_TOKEN>"
   ```

   Confirm with `GET` on the same URL that your app (not just Meta's own "WA
   DevX Webhook Events" app) appears in the response. Skipping this step is a
   common cause of a webhook that verifies fine and passes the Dashboard
   "Test" button, yet never receives real customer messages — the Test button
   injects payloads directly and does not depend on this subscription.
7. Use the same verify token in Meta and `META_WEBHOOK_VERIFY_TOKEN`.
8. Configure the app secret and enable signature validation.

## Template payload contract

For the current configuration, the application sends:

```json
{
  "messaging_product": "whatsapp",
  "to": "201000000000",
  "type": "template",
  "template": {
    "name": "itqan_lead_outreach",
    "language": {"code": "ar"},
    "components": [{
      "type": "body",
      "parameters": [{"type": "text", "text": "Ahmed"}]
    }]
  }
}
```

The name, language, component order, and parameter count must exactly match the
Active template. A mismatch is rejected by Meta.

## Consent and conversation windows

An approved template does not replace user consent. Retain the consent source,
time, wording, and policy version outside this MVP before sending. Free-form
text should be sent only inside the customer-service conversation window. The
`/api/test-text` endpoint is strictly a diagnostic tool for that situation.
`/api/outreach/bulk` (the dashboard's "Bulk Template Outreach") sends a saved
local Message Template as free-form text too, so it shares this restriction —
recipients outside an open window are rejected by Meta and reported as failed
per recipient, not silently skipped. It does not use the Meta-approved
template mechanism; that remains available only via the single-recipient
`/api/outreach` endpoint ("Send approved template" in the dashboard).

## Webhook security and retry behavior

Set `META_VALIDATE_SIGNATURE=true` in production. Meta may deliver the same
webhook repeatedly, so inbound message IDs are deduplicated. Delivery status
events (`sent`, `delivered`, `read`, and `failed`) are stored as message-event
rows correlated by Meta message ID.
