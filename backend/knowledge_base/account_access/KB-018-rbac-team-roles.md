---
id: KB-018
title: RBAC and Team Roles
category: account_access
tags: [rbac, roles, permissions, account, security]
last_updated: 2026-04-22
applies_to: [Pro, Enterprise]
---

# RBAC and Team Roles

CloudDash uses role-based access control (RBAC) to manage what each team member can see and do.

## Section 1 — Built-in roles

Every workspace has these built-in roles:

| Role | Permissions |
|---|---|
| **Owner** | Everything, including billing, plan changes, deleting the workspace. Cannot be removed by other admins. |
| **Admin** | Everything except billing and plan changes. Can manage users, integrations, alerts, dashboards. |
| **Editor** | Create / modify / delete alerts, dashboards. Cannot manage users or integrations. |
| **Viewer** | Read-only access to all dashboards and alert rules. Cannot trigger or modify anything. |

Free and Starter plans use these built-in roles only.

## Section 2 — Custom roles (Enterprise)

Enterprise plans can define custom roles with arbitrary scope sets. Each scope corresponds to an action category:

- `billing:read`, `billing:write`
- `integration:read`, `integration:write`
- `alert:read`, `alert:write`, `alert:resolve`
- `dashboard:read`, `dashboard:write`
- `user:invite`, `user:remove`, `user:role_change`
- `audit:read`, `audit:export`
- `api_key:create`, `api_key:revoke`

Example custom role: an "On-call Responder" with `alert:read` + `alert:resolve` + `dashboard:read` and nothing else.

## Section 3 — Mapping IdP groups to roles

When SSO is configured (KB-017), you map IdP groups to CloudDash roles:

1. **Settings → Account → SSO → Group mapping**.
2. Add a row: `engineering-managers → Admin`, `engineers → Editor`, `support → Viewer`, etc.
3. Click **Save**.

A user can be in multiple groups; their effective permissions are the **union** of all matched roles.

## Section 4 — API keys and scopes

API keys (see KB-001 and KB-014) have their own scope system. A user creating an API key can grant only scopes their own role permits — i.e. an Editor cannot create an API key with `billing:write`.

## Section 5 — Audit logging of role changes

Every role assignment, role change, and removal is logged in the audit log (see KB-019). The log records who made the change, when, and the before/after state.

## Section 6 — Related articles

- KB-017: Configuring SSO
- KB-019: Viewing audit logs
- KB-003: Inviting team members
- KB-014: API authentication and rate limits
