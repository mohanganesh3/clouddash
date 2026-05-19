---
id: KB-015
title: Webhook Configuration
category: api_docs
tags: [api, webhooks, integrations]
last_updated: 2026-04-12
applies_to: [Pro, Enterprise]
---

# Webhook Configuration

CloudDash can POST events to your HTTP endpoint when alerts fire, integrations change state, or audit events occur. Webhooks are available on Pro and Enterprise plans.

## Section 1 — Creating a webhook

1. **Settings → Integrations → Webhooks → New webhook**.
2. Enter your endpoint URL (must be HTTPS).
3. Choose events to subscribe to (see Section 3).
4. Optionally set a **signing secret** (recommended).
5. Click **Save and send test**.

The test sends a `webhook.test` event to your URL. Confirm your endpoint returned HTTP 2xx within 5 seconds.

## Section 2 — Payload structure

```json
{
  "event_id": "evt_01H...",
  "event_type": "alert.fired",
  "timestamp": "2026-05-13T10:23:01Z",
  "workspace_id": "ws_acme",
  "data": {
    "alert_id": "alr_...",
    "alert_name": "High API Error Rate",
    "severity": "critical",
    "current_value": 13.4,
    "threshold": 5.0
  },
  "signature": "sha256=...",
  "delivery_attempt": 1
}
```

## Section 3 — Available events

- `alert.fired` — an alert rule transitioned to firing
- `alert.resolved` — an alert recovered
- `alert.ack` — a teammate acknowledged an alert
- `integration.health_changed` — an integration went unhealthy or recovered
- `audit.user_invited`, `audit.user_removed`, `audit.role_changed`
- `billing.invoice_finalized`, `billing.payment_failed`

## Section 4 — Verifying signatures

If you set a signing secret, CloudDash includes a `signature` field. Verify it server-side:

```python
import hmac, hashlib

def verify(payload_bytes: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)
```

## Section 5 — Retries and delivery guarantees

If your endpoint returns non-2xx or times out (5s), CloudDash retries with exponential backoff: 30s, 2m, 10m, 1h, 6h, 24h. After 6 failed attempts, the event is dropped and the webhook is marked **Degraded** in the UI.

To replay a failed delivery: **Settings → Integrations → Webhooks → \[your webhook\] → Failed deliveries → Replay**.

## Section 6 — Best practices

1. Return 2xx as quickly as possible — accept then process asynchronously.
2. Verify signatures.
3. Implement idempotency on `event_id` — duplicates are possible during retries.
4. Use HTTPS with a valid certificate.

## Section 7 — Related articles

- KB-014: API authentication and rate limits
- KB-016: Python SDK quickstart
