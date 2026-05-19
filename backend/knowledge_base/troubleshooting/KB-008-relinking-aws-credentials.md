---
id: KB-008
title: Re-linking AWS Credentials After Rotation
category: troubleshooting
tags: [aws, integrations, credentials, rotation, security]
last_updated: 2026-04-25
applies_to: [Starter, Pro, Enterprise]
---

# Re-linking AWS Credentials After Rotation

AWS recommends rotating IAM credentials regularly. This article explains how to re-authorize CloudDash after such a rotation **without losing alert history, dashboards, or audit logs**.

## Section 1 — When you need this guide

Use this guide if any of the following happened recently:

- You rotated the access keys attached to the IAM role CloudDash assumes.
- You re-created the IAM role and got a new role ARN.
- You see status **Unauthorized** on the AWS integration page after a credential change.
- Alert rules tied to AWS metrics suddenly stopped firing — see KB-005 for symptoms.

## Section 2 — What you need before starting

Have these on hand:

1. The **new role ARN** (from your AWS IAM console).
2. The CloudDash **External ID** for this integration. To retrieve it without breaking the integration:
   - **Settings → Integrations → AWS → View setup details**.
   - The External ID is shown but partially masked. Click **Reveal** (Pro/Enterprise admins only).
3. CloudDash admin access. Re-linking requires the `integration:write` permission. See KB-018 for RBAC details.

## Section 3 — Step-by-step

### Step 1: Verify the new role's trust policy

The new role's trust policy MUST still reference the CloudDash AWS account `886499874111` and the SAME External ID as before. If the External ID changed, the integration will be treated as new and you will lose alert binding history.

### Step 2: Update the role ARN in CloudDash

1. **Settings → Integrations → AWS → Re-link**.
2. Paste the new role ARN.
3. Confirm the External ID field shows your existing External ID (do NOT regenerate).
4. Click **Verify**.

CloudDash performs a live `sts:AssumeRole` and a test metric fetch. On success, the status flips from red to green within 10 seconds.

### Step 3: Confirm metrics are flowing

1. Open any dashboard tied to AWS metrics.
2. Confirm the latest data point timestamp is within the last 5 minutes (or 1 minute on Pro/Enterprise).
3. Open one alert rule that depends on AWS metrics and confirm its **Last Evaluation** timestamp updated.

### Step 4: Re-arm any silenced alerts

While the integration was unhealthy, CloudDash silenced alert rules to avoid false-negative noise. Manually re-arm them:

1. **Alerts → Filtered by: Silenced (auto)**.
2. Bulk-select and click **Resume**.

## Section 4 — Common pitfalls

- **Regenerating the External ID**: this creates a NEW integration record. You will see duplicated AWS accounts in your integration list and lose the binding from existing alerts. If you accidentally did this, contact support to merge.
- **Skipping the verification step**: re-linking does NOT auto-verify if you click "Save" without "Verify". The integration may appear connected but fail on the next scan.
- **Rotating the role too quickly**: AWS propagates IAM changes asynchronously. If you rotate credentials and immediately re-link in CloudDash, the verify step may fail with `InvalidClientTokenId`. Wait 60 seconds and retry.

## Section 5 — Recommended rotation cadence

For Pro and Enterprise customers, we recommend automating credential rotation:

- Use **AWS Secrets Manager** with automatic rotation Lambda for the role's external session.
- Schedule rotation every **90 days** (AWS default recommendation).
- Trigger the CloudDash re-link via our API after each rotation. See KB-014 for API authentication and the `POST /api/v1/integrations/aws/relink` endpoint.

## Section 6 — Related articles

- KB-005: Troubleshooting — Alerts not firing
- KB-007: AWS CloudWatch integration failing
- KB-014: API authentication and rate limits
- KB-018: RBAC and team roles
