---
id: KB-014
title: API Authentication and Rate Limits
category: api_docs
tags: [api, authentication, rate-limits, security]
last_updated: 2026-04-05
applies_to: [Starter, Pro, Enterprise]
---

# API Authentication and Rate Limits

CloudDash exposes a JSON REST API at `https://api.clouddash.com/api/v1`. This article covers how to authenticate, the rate limits per plan, and best practices.

## Section 1 — Authentication

All API requests require an API key in the `Authorization` header:

```
Authorization: Bearer cd_live_<your-key>
```

API keys are managed under **Settings → API Keys**. See KB-001 for how to rotate them.

Example request:

```bash
curl -H "Authorization: Bearer cd_live_..." \
     https://api.clouddash.com/api/v1/alerts
```

## Section 2 — Rate limits

| Plan | Requests per minute | Burst |
|---|---|---|
| Free | 30 | 60 |
| Starter | 120 | 240 |
| Pro | 600 | 1200 |
| Enterprise | Custom (default 3000) | Custom |

The limits are per workspace, not per key. Use the response headers to track:

- `X-RateLimit-Limit`: the limit per minute for your plan.
- `X-RateLimit-Remaining`: how many you have left in the current window.
- `X-RateLimit-Reset`: Unix epoch seconds when the window resets.

When you hit the limit, the API returns HTTP 429 with `Retry-After` in the response.

## Section 3 — Endpoints overview

| Method + path | Description |
|---|---|
| `GET /api/v1/alerts` | List alert rules |
| `POST /api/v1/alerts` | Create an alert rule |
| `GET /api/v1/alerts/{id}` | Get a specific rule |
| `PATCH /api/v1/alerts/{id}` | Update a rule |
| `DELETE /api/v1/alerts/{id}` | Delete a rule |
| `GET /api/v1/dashboards` | List dashboards |
| `POST /api/v1/integrations/aws/relink` | Re-link AWS credentials (see KB-008) |
| `GET /api/v1/audit-log` | Stream audit events (Pro+) |
| `POST /api/v1/webhooks` | Manage webhook subscriptions (see KB-015) |

Full OpenAPI spec at `https://api.clouddash.com/openapi.json`.

## Section 4 — Errors

CloudDash returns standard HTTP status codes plus a structured error body:

```json
{
  "error": {
    "code": "INVALID_THRESHOLD",
    "message": "Threshold must be a non-negative number",
    "request_id": "req_abc123"
  }
}
```

Always log the `request_id` — it lets support trace your request quickly.

## Section 5 — Best practices

1. **Rotate keys quarterly** (KB-001).
2. **Use scoped keys**: `read:metrics` for dashboards, `write:alerts` for CI/CD pipelines that manage rules-as-code.
3. **Implement retry-with-backoff** on HTTP 429 and 5xx. The official SDKs do this automatically (KB-016).
4. **Pin your client to the API version** — currently `v1`. We will give 6 months' notice before deprecating `v1`.

## Section 6 — Related articles

- KB-001: How to reset your API key
- KB-015: Webhook configuration
- KB-016: Python SDK quickstart
