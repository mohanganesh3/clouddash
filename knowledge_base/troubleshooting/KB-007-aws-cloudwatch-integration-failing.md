---
id: KB-007
title: Troubleshooting — AWS CloudWatch Integration Failing
category: troubleshooting
tags: [aws, integrations, cloudwatch, troubleshooting]
last_updated: 2026-04-30
applies_to: [Starter, Pro, Enterprise]
---

# Troubleshooting — AWS CloudWatch Integration Failing

When CloudDash cannot pull metrics from your AWS account, the **Settings → Integrations → AWS** page shows a red **Unhealthy** status and dependent alert rules silently stop evaluating. This guide covers the four most common failure modes.

## Section 1 — Verify the integration role still exists

CloudDash uses an AWS IAM role (assumed via the CloudDash AWS account ID `886499874111`) to read CloudWatch metrics. If the role was deleted or its trust policy was modified, the integration fails immediately.

1. In your AWS console, navigate to **IAM → Roles** and confirm a role named `CloudDashIntegrationRole` (or whatever name you chose) exists.
2. Open the role's **Trust relationships** tab and confirm it allows the CloudDash AWS account to assume it. The trust policy should contain:

```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::886499874111:root" },
  "Action": "sts:AssumeRole",
  "Condition": {
    "StringEquals": { "sts:ExternalId": "<your-clouddash-external-id>" }
  }
}
```

The **External ID** is unique per CloudDash workspace and is shown on the AWS integration setup screen.

## Section 2 — Verify the IAM permissions

The role must have at minimum the AWS-managed policy `CloudWatchReadOnlyAccess`. For full feature support (Cost Explorer, EC2 inventory), attach:

- `CloudWatchReadOnlyAccess`
- `AWSBillingReadOnlyAccess`
- `AmazonEC2ReadOnlyAccess`

Common mistake: applying these policies to a *user* instead of the *role*. CloudDash assumes the role; the user policies do not apply.

## Section 3 — Re-link rotated credentials

If you rotated the access keys associated with the IAM role (AWS recommends rotation every 90 days), or if you re-created the role with a new ARN, you must re-link CloudDash:

1. Open **CloudDash → Settings → Integrations → AWS**.
2. Click **Re-link**.
3. Enter the **new role ARN** and the **same External ID** (the External ID does not change when you rotate credentials — only when you delete and recreate the integration).
4. Click **Verify**. CloudDash will perform a `sts:AssumeRole` and fetch a sample metric. A green checkmark confirms success.

If you forget the External ID, see KB-008 for how to retrieve it without losing your alert history.

## Section 4 — Region and account misalignment

CloudDash polls one or more AWS regions per integration. If you recently launched workloads in a region the integration is not configured to scan, no metrics will appear.

**Fix**:
1. **Settings → Integrations → AWS → Edit**.
2. In **Regions to monitor**, add the missing region(s).
3. Click **Save**. The first scan completes within 5–10 minutes for new regions.

## Section 5 — Throttling and rate limits

AWS imposes per-region CloudWatch API throttles. If you are on the Starter plan and have many resources, you may hit `Rate exceeded` errors that show up as intermittent **Degraded** status (yellow).

**Fix options**:
- Reduce **scan frequency** under **Settings → Integrations → AWS → Advanced** (default: 60s; can be raised to 300s).
- Upgrade to **Pro** or **Enterprise**, which uses CloudDash's pooled API quota.
- Open an AWS support case to request a CloudWatch API limit increase.

## Section 6 — Verifying the fix

After applying any of the above, click **Test Connection** on the AWS integration page. A successful test:

1. Performs a live `sts:AssumeRole`.
2. Fetches one CloudWatch metric (typically `AWS/EC2 CPUUtilization`).
3. Lists the regions actually returning data.

If the test passes but alerts still are not firing, see KB-005 *Alerts not firing*.
