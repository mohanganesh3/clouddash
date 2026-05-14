---
id: KB-003
title: How Do I Invite Team Members to My CloudDash Workspace?
category: faqs
tags: [team, users, invite, onboarding, faq, account]
last_updated: 2026-04-12
applies_to: [Free, Starter, Pro, Enterprise]
---

# How Do I Invite Team Members to My CloudDash Workspace?

CloudDash supports collaborative monitoring across teams. Inviting a team member takes under a minute on any plan.

## Section 1 — Per-plan user limits

| Plan | Included users | Add-on cost |
|---|---|---|
| Free | 1 | n/a — upgrade to add users |
| Starter | Up to 5 | n/a — upgrade to add more |
| Pro | Up to 25, then $10/user/month | $10/user/month over 25 |
| Enterprise | Custom (typically unlimited) | Negotiated in contract |

## Section 2 — Inviting via email (no SSO)

1. **Settings → Team → Invite member**.
2. Enter the user's email address.
3. Choose a role (see KB-018 for the available roles).
4. Optionally add a personal note.
5. Click **Send invite**.

The invitee receives an email with a magic link valid for 72 hours. After they accept, they will be prompted to set up their account.

## Section 3 — Bulk invite (CSV)

For inviting many users at once:

1. **Settings → Team → Bulk invite**.
2. Upload a CSV with columns `email,role,team` (team is optional).
3. Confirm preview, click **Send all**.

Maximum 200 invites per CSV. Pro and Enterprise only.

## Section 4 — SSO and SCIM (auto-provisioning)

If your workspace uses SSO with SCIM (Pro and Enterprise), users are provisioned and deprovisioned automatically based on IdP group membership. You do not need to manually invite SSO-provisioned users — assigning them to your CloudDash group in your IdP is sufficient.

See KB-017 for SSO setup and KB-018 for group-to-role mapping.

## Section 5 — Pending invites

To see invites that have not yet been accepted:

1. **Settings → Team → Pending invites**.
2. From here you can resend or revoke an invite.

## Section 6 — Related articles

- KB-017: Configuring SSO
- KB-018: RBAC and team roles
