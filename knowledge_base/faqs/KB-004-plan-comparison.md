---
id: KB-004
title: What's the Difference Between Free, Starter, Pro, and Enterprise?
category: faqs
tags: [billing, plans, pricing, comparison, faq]
last_updated: 2026-04-15
applies_to: [Free, Starter, Pro, Enterprise]
---

# What's the Difference Between Free, Starter, Pro, and Enterprise?

This article gives a feature-by-feature comparison of CloudDash's four plan tiers. For pricing, see KB-010 § 1.

## Section 1 — At a glance

| | Free | Starter | Pro | Enterprise |
|---|---|---|---|---|
| Price | $0 | $29/mo | $149/mo | Custom |
| Users | 1 | 5 | 25 (then $10/user) | Unlimited |
| Cloud providers | AWS only | AWS + GCP + Azure | All + Kubernetes | All + custom integrations |
| Metric retention | 7 days | 30 days | 90 days | Custom (up to 2 years) |
| Alert rules | 5 | 50 | 500 | Unlimited |
| Notification channels | Email only | + Slack | + PagerDuty, Teams, webhooks | + custom routing |
| SSO (SAML/OIDC) | — | — | ✓ | ✓ + SCIM auto-provisioning |
| RBAC | Single role | 3 roles | 3 roles + custom | Fully custom |
| Audit log | — | 30 days | 90 days | Custom + export |
| Support | Community | Email (24h) | Email + chat (4h business) | Dedicated CSM + 1h SLA |

## Section 2 — Who should pick which plan

- **Free**: solo developer, one AWS account, evaluation. Limited to 5 alert rules — fine for personal projects.
- **Starter**: small startup, multi-cloud, up to 5 engineers. Adds Slack and 30-day retention.
- **Pro**: growing engineering team, 5–25 engineers, needs SSO, RBAC, and longer retention. The most popular plan.
- **Enterprise**: 25+ engineers, regulated industry, custom retention or SLA needs. Includes a dedicated Customer Success Manager.

## Section 3 — Key Pro features (most-asked)

These are the features most commonly cited as reasons to upgrade from Starter to Pro:

- SSO (SAML and OIDC).
- 90-day metric retention (vs. 30 days on Starter).
- Cross-cloud dashboard joins.
- Audit log access.
- Webhook notification channels.
- Pooled API quota (avoids per-user CloudWatch throttling — see KB-007 § 5).

## Section 4 — Key Enterprise features

These differentiate Enterprise from Pro:

- SCIM for automatic user provisioning/deprovisioning.
- Custom data retention (up to 2 years).
- Custom RBAC roles (define your own scope sets).
- Dedicated Customer Success Manager.
- Contractual SLA (1-hour response on P1).
- Audit log export to your S3 / GCS / Azure Storage.
- IP allowlisting for the API.

## Section 5 — Related articles

- KB-010: How to upgrade your plan
- KB-018: RBAC and team roles
- KB-017: Configuring SSO
