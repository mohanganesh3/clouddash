---
id: KB-010
title: How to Upgrade Your CloudDash Plan
category: billing
tags: [billing, plans, upgrade, enterprise, pro]
last_updated: 2026-04-10
applies_to: [Free, Starter, Pro, Enterprise]
---

# How to Upgrade Your CloudDash Plan

This guide walks through upgrading between CloudDash plans and explains how billing changes when you upgrade mid-cycle.

## Section 1 — Plan tiers at a glance

| Plan | Price (per workspace, billed monthly) | Best for |
|---|---|---|
| Free | $0 | Solo developers, evaluations |
| Starter | $29/mo | Small teams up to 5 users |
| Pro | $149/mo | Growing teams, multi-cloud (AWS + GCP + Azure), SSO, RBAC |
| Enterprise | Custom (starting $999/mo) | Larger orgs, SAML/OIDC SSO with SCIM, audit-log export, custom retention, dedicated support |

For a feature-by-feature comparison, see KB-004.

## Section 2 — Self-service upgrade (Free → Starter, Starter → Pro)

These upgrades are immediate and self-service:

1. **Settings → Billing → Change plan**.
2. Choose your target plan.
3. Confirm payment method (or add one if upgrading from Free).
4. Click **Upgrade now**.

The plan changes within 60 seconds. Billing for the current cycle is prorated (see Section 4).

## Section 3 — Upgrading to Enterprise

Enterprise pricing is custom and depends on:

- Number of users.
- Data retention requirements (90 days, 1 year, or custom).
- SSO type (SAML or OIDC + SCIM).
- Whether you need a dedicated Customer Success Manager.
- Required SLA tier.

To upgrade to Enterprise:

1. **Settings → Billing → Contact Sales** OR email `sales@clouddash.com`.
2. A sales engineer schedules a 30-minute scoping call.
3. After the call, you receive a custom quote within 2 business days.
4. On agreement, sales sends a contract via DocuSign.
5. Once signed, your workspace is upgraded within 1 business day.

Existing dashboards, alert rules, integrations, and audit logs are preserved through the upgrade — no data migration needed.

## Section 4 — How mid-cycle billing works

When you upgrade mid-cycle, you are charged a prorated difference between your old plan and your new plan, calculated daily.

**Worked example**:
- You are on Pro ($149/mo), billed on the 1st of the month.
- On the 16th, you upgrade to Enterprise at a quoted $999/mo.
- Days remaining in the cycle: 15 of 30 = 50%.
- Prorated charge: ($999 − $149) × 50% = **$425.00**.
- This is charged immediately as a one-time line item on your next invoice.
- Starting the 1st of next month, you are billed $999/mo at the regular cadence.

You will see TWO line items on your next invoice: one for the prorated upgrade ($425) and one for the new month at the new rate ($999). This is NOT a duplicate charge — see KB-012 if you suspect a real duplicate.

## Section 5 — When the upgrade takes effect

- **Self-service upgrades**: features unlock within 60 seconds. Existing alerts, dashboards, and integrations continue uninterrupted.
- **Enterprise upgrades**: features unlock within 1 business day after contract signature. SSO/SCIM provisioning is configured during the onboarding call.
- **Open issues across plans**: if you have an open support ticket or an unresolved technical issue at the time of upgrade, the issue and its full conversation history is preserved across the plan change. The receiving Customer Success Manager (Enterprise) will see the prior context.

## Section 6 — Downgrading

Downgrades take effect at the **end of your current billing cycle** — you keep paid features until then. To downgrade:

1. **Settings → Billing → Change plan → choose lower plan**.
2. Confirm the downgrade.

You will not be refunded for the unused portion of the current cycle (see KB-011 § 4 for the policy rationale). Instead, the unused value is credited toward your next invoice.

## Section 7 — Related articles

- KB-004: Plan comparison (Free / Starter / Pro / Enterprise feature matrix)
- KB-011: Refund policy
- KB-012: Resolving duplicate charges
- KB-013: Invoice format and how to read it
