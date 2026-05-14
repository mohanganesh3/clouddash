---
id: KB-017
title: Configuring SSO with Okta, Azure AD, and Other Providers
category: account_access
tags: [sso, saml, oidc, okta, azure-ad, account, security]
last_updated: 2026-04-28
applies_to: [Pro, Enterprise]
---

# Configuring SSO with Okta, Azure AD, and Other Providers

Single Sign-On (SSO) is available on Pro and Enterprise plans. CloudDash supports SAML 2.0 and OpenID Connect (OIDC). SCIM auto-provisioning is available on Enterprise.

## Section 1 — Provider support

Tested first-party setup guides exist for:

- **Okta** (SAML and OIDC)
- **Microsoft Entra ID / Azure AD** (SAML and OIDC)
- **Google Workspace** (OIDC)
- **OneLogin** (SAML)
- **JumpCloud** (SAML)
- **Auth0** (SAML and OIDC)

Any IdP that exposes a SAML 2.0 metadata URL or OIDC discovery document also works.

## Section 2 — Setup overview

1. **Settings → Account → SSO → Configure**.
2. Choose your protocol (SAML or OIDC).
3. CloudDash shows your **Service Provider metadata** — copy the values into your IdP:
   - Entity ID / Audience: `https://app.clouddash.com/sso/<workspace-id>`
   - ACS / Reply URL: `https://app.clouddash.com/sso/saml/callback`
   - For OIDC: the redirect URI is `https://app.clouddash.com/sso/oidc/callback`.
4. In your IdP, create a CloudDash app and assign the users/groups who should have access.
5. Copy your IdP's metadata (URL or XML) and paste it into CloudDash.
6. Map IdP groups to CloudDash roles (see KB-018).
7. Click **Verify and Activate**.

CloudDash will perform a test handshake. Once verified, all users in the assigned IdP groups can sign in via your CloudDash login URL.

## Section 3 — SCIM provisioning (Enterprise only)

SCIM lets your IdP automatically provision and deprovision CloudDash users:

1. **Settings → Account → SSO → SCIM → Generate token**.
2. Copy the SCIM endpoint URL and bearer token.
3. In your IdP's CloudDash app, configure SCIM with these values.
4. Push your initial set of users.

After SCIM is wired up, when you add or remove a user from the CloudDash group in your IdP, the change is reflected in CloudDash within 60 seconds.

## Section 4 — Domain claims

You must claim the email domain(s) that your SSO users belong to. **Settings → Account → Domains → Add**. Verification is via DNS TXT record.

## Section 5 — Disabling password login

After SSO is verified, you can require all users to sign in via SSO (no password fallback). **Settings → Account → SSO → Enforce SSO**. Note: at least one workspace owner is exempted from this enforcement so you can recover access if the IdP is misconfigured.

## Section 6 — Troubleshooting

If users cannot sign in after SSO setup, see KB-009 for the troubleshooting flow.

## Section 7 — Related articles

- KB-009: SSO sign-in failures
- KB-018: RBAC and team roles
- KB-003: Inviting team members
