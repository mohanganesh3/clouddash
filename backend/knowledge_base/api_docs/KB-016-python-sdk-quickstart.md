---
id: KB-016
title: Python SDK Quickstart
category: api_docs
tags: [api, sdk, python, quickstart]
last_updated: 2026-04-18
applies_to: [Free, Starter, Pro, Enterprise]
---

# Python SDK Quickstart

The official `clouddash-python` SDK wraps the REST API with retry-with-backoff, response model parsing, and async support.

## Section 1 — Install

```bash
pip install clouddash
```

Requires Python 3.10+.

## Section 2 — Authenticate

```python
from clouddash import CloudDash

client = CloudDash(api_key="cd_live_...")  # or via CLOUDDASH_API_KEY env var
```

If `api_key` is omitted, the SDK reads `CLOUDDASH_API_KEY` from the environment.

## Section 3 — Common operations

### List alert rules

```python
rules = client.alerts.list()
for rule in rules:
    print(rule.id, rule.name, rule.is_enabled)
```

### Create an alert rule

```python
rule = client.alerts.create(
    name="High API Error Rate",
    metric="api.requests.errors_per_min",
    threshold=5.0,
    operator="gt",
    evaluation_window_minutes=10,
    notification_channel_ids=["nch_slack_oncall"],
)
print("Created:", rule.id)
```

### Re-link AWS integration after credential rotation

```python
client.integrations.aws.relink(
    role_arn="arn:aws:iam::123456789012:role/CloudDashIntegrationRole",
    external_id="cd_ext_...",
)
```

### Stream the audit log

```python
for event in client.audit_log.stream(since="2026-04-01T00:00:00Z"):
    print(event.timestamp, event.actor.email, event.action, event.target)
```

## Section 4 — Async support

```python
import asyncio
from clouddash import AsyncCloudDash

async def main():
    async with AsyncCloudDash(api_key="cd_live_...") as client:
        rules = await client.alerts.list()
        print(rules)

asyncio.run(main())
```

## Section 5 — Errors and retries

The SDK raises typed exceptions:

- `CloudDashRateLimitError` (HTTP 429)
- `CloudDashAuthError` (HTTP 401, 403)
- `CloudDashNotFoundError` (HTTP 404)
- `CloudDashServerError` (HTTP 5xx)

Retries are automatic on 429 and 5xx with exponential backoff (max 5 attempts by default; configurable).

## Section 6 — Pinning the API version

```python
client = CloudDash(api_key="...", api_version="v1")
```

We will support `v1` for at least 12 more months. Plan migrations are announced 6 months in advance.

## Section 7 — Related articles

- KB-014: API authentication and rate limits
- KB-015: Webhook configuration
