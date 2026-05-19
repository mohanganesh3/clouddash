---
id: KB-019
title: Viewing and Exporting Audit Logs
category: account_access
tags: [audit, logs, compliance, security, account]
last_updated: 2026-04-30
applies_to: [Starter, Pro, Enterprise]
---

# Viewing and Exporting Audit Logs

CloudDash records every administrative action in an audit log so you can review who did what, when, and from where. Retention varies by plan.

## Section 1 — Retention by plan

| Plan | Retention |
|---|---|
| Free | Not available |
| Starter | 30 days |
| Pro | 90 days |
| Enterprise | Custom (default 365 days, up to 2 years) |

Enterprise can additionally export the audit log to S3 / GCS / Azure Storage for indefinite retention.

## Section 2 — What gets logged

- User invitations, role changes, removals
- API key creation and revocation
- Integration connect / re-link / disconnect (e.g. AWS — KB-008)
- Alert rule create / modify / delete / pause
- Dashboard create / modify / delete
- SSO configuration changes (KB-017)
- Webhook subscription changes (KB-015)
- Login successes and failures (Pro+)
- Plan changes and billing actions
- Audit-log export events themselves

Each event records: `timestamp` (UTC, microsecond precision), `actor` (user or API key), `action`, `target_resource`, `before/after diff`, `source IP`, `user agent`, `request_id`.

## Section 3 — Viewing in the UI

1. **Settings → Account → Audit log**.
2. Filter by actor, action, time range, or resource.
3. Click any event to expand the full diff.

## Section 4 — Streaming via API

Pro and Enterprise can stream the audit log via the API:

```python
for event in client.audit_log.stream(since="2026-05-01T00:00:00Z"):
    print(event)
```

See KB-016 for SDK setup.

## Section 5 — Continuous export (Enterprise)

Enterprise can configure continuous export to:

- AWS S3 (with assume-role)
- GCP Cloud Storage (service-account)
- Azure Blob Storage (managed identity or SAS)

Format: one JSON object per line (NDJSON / JSONL), one file per hour. Configure under **Settings → Account → Audit log → Continuous export**.

## Section 6 — Compliance use cases

Audit logs satisfy the access-tracking requirements of:

- SOC 2 Type II
- ISO 27001
- HIPAA (with a signed BAA — Enterprise only)
- GDPR (combined with our DPA)

## Section 7 — Related articles

- KB-018: RBAC and team roles
- KB-017: Configuring SSO
- KB-001: How to reset your API key
