---
id: KB-009
title: Troubleshooting — SSO Sign-in Failures
category: troubleshooting
tags: [sso, saml, oidc, authentication, troubleshooting, account]
last_updated: 2026-05-02
applies_to: [Pro, Enterprise]
---

# Troubleshooting — SSO Sign-in Failures

If users in your organization cannot sign in via SSO, work through this guide in order. SSO is available on the Pro and Enterprise plans. CloudDash supports SAML 2.0 and OIDC; common providers include Okta, Azure AD (Microsoft Entra ID), Google Workspace, OneLogin, JumpCloud, and any IdP that exposes a SAML 2.0 metadata endpoint.

## Section 1 — Symptom check

| Symptom | Likely cause | Section |
|---|---|---|
| Users see "SSO not configured" | IdP metadata never imported or was deleted | Section 2 |
| Users land on IdP, authenticate, then get "Access denied" by CloudDash | Group/role mapping mismatch | Section 3 |
| Users see "Signature does not match" or "AuthnRequest invalid" | Clock skew or certificate rotation | Section 4 |
| Specific users denied; others succeed | SCIM deprovisioning or group membership | Section 5 |
| New domain emails cannot SSO | Domain claim not verified | Section 6 |

## Section 2 — IdP metadata not configured

1. Go to **Settings → Account → SSO**.
2. Confirm **Status: Active** and **Provider** matches your actual IdP.
3. If the metadata URL or XML is missing, re-import it. For Okta: copy the **Identity Provider metadata** URL from your CloudDash app in Okta → paste into CloudDash → click **Save and Verify**.

## Section 3 — Group / role mapping mismatch

CloudDash maps IdP groups to roles using attribute statements. The default attribute name is `groups`. If your IdP sends the attribute as `memberOf` or `Role`, change the mapping:

1. **Settings → Account → SSO → Attribute mappings**.
2. Set **Group attribute** to whatever your IdP sends (case-sensitive).
3. Confirm at least one group mapping is configured. Without a mapping, the user is denied because no role can be assigned.

To debug: open **Settings → Account → SSO → Debug → Last login attempt**. CloudDash shows the raw SAML/OIDC attribute set received from your IdP for the most recent failed attempt. If your expected group is missing from the attribute set, the issue is on the IdP side.

## Section 4 — Certificate rotation or clock skew

SAML signatures rely on the IdP's signing certificate. When the IdP rotates its cert, CloudDash must re-import metadata.

1. Re-import the IdP metadata URL — this re-fetches the new cert.
2. Verify your server clocks. SAML allows ≤ 5 minutes of clock skew between IdP and SP. If your IdP's NotBefore/NotOnOrAfter timestamps are outside the window, all logins fail.

## Section 5 — User-specific denials

If only certain users fail:

1. Confirm the user is **active** in your IdP (Okta: not Suspended; Azure AD: not Disabled).
2. Confirm the user has **at least one group** that maps to a CloudDash role.
3. If you use SCIM provisioning, check **Settings → Account → SCIM → Audit log** — a recent deprovisioning event will explain it.

## Section 6 — Domain claim not verified

SSO is restricted to email domains your organization has claimed. If a user has an email like `alice@subsidiary.com` but only `parent.com` is claimed, the user is rejected.

1. **Settings → Account → Domains**.
2. Add the new domain.
3. Verify ownership via DNS TXT record (CloudDash provides the record value).
4. After verification (typically 5 minutes), the user can sign in.

## Section 7 — Escalating to support

If sign-in still fails after these steps, contact support with:

- Your CloudDash workspace ID.
- The **Trace ID** of a failed login attempt (visible in the SSO Debug panel).
- A SAML trace from your IdP (use the SAML-tracer browser extension).

See also KB-017 for the original SSO setup guide and KB-018 for RBAC role mapping.
