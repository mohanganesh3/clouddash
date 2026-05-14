---
id: KB-001
title: How Do I Reset My CloudDash API Key?
category: faqs
tags: [api, authentication, security, faq]
last_updated: 2026-04-08
applies_to: [Free, Starter, Pro, Enterprise]
---

# How Do I Reset My CloudDash API Key?

CloudDash API keys grant programmatic access to your workspace. You should rotate your API key immediately if you suspect it has been exposed (committed to a public repo, shared in chat, etc.) and on a regular schedule (every 90 days is recommended).

## Section 1 — Quick rotation (no downtime)

For most use cases, follow this dual-key rotation procedure to avoid any service interruption:

1. Open **Settings → API Keys**.
2. Click **Create new key**. Give it a descriptive name (e.g. `prod-api-2026-05`) and the same scopes as your current key.
3. Copy the new key. **This is the only time the full key is shown.**
4. Update your application or CI/CD secret store with the new key.
5. After confirming everything works on the new key (give it 5–10 minutes), revoke the old key from **Settings → API Keys → Revoke**.

## Section 2 — Emergency rotation (if a key is compromised)

If your key is actively leaked, prioritize revocation over zero-downtime:

1. **Settings → API Keys → Revoke** on the compromised key. This invalidates it within 30 seconds.
2. Create a new key as in Section 1.
3. Update applications. Expect brief service errors during the window between revocation and update.

CloudDash will email all admins of the workspace when an API key is revoked, including the key name and the user who revoked it.

## Section 3 — Scopes and permissions

API keys can be scoped to limit blast radius. Available scopes:

- `read:metrics` — read-only access to metrics and dashboards.
- `read:alerts` — read alert rules and history.
- `write:alerts` — create / modify / delete alert rules.
- `write:integrations` — manage cloud-provider integrations.
- `admin` — full workspace access (rare; use sparingly).

By default a new key has only `read:metrics` and `read:alerts`. Add `write:` scopes only when needed.

## Section 4 — Where to find the API key

Once created, the FULL key is shown only once at creation time. After that, you can see only the last 4 characters of the key for identification. If you lose the full key, you must create a new one.

## Section 5 — Related articles

- KB-014: API authentication and rate limits
- KB-018: RBAC and team roles
- KB-019: Viewing audit logs (to see when a key was used)
