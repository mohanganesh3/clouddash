---
id: KB-005
title: Troubleshooting — Alerts Are Not Firing
category: troubleshooting
tags: [alerts, troubleshooting, monitoring, integrations]
last_updated: 2026-04-22
applies_to: [Starter, Pro, Enterprise]
---

# Troubleshooting — Alerts Are Not Firing

If your CloudDash alerts have stopped firing or you are not receiving notifications you previously received, work through the steps below in order. Most alert issues fall into one of four root causes: stale integration credentials, a paused alert rule, a notification-channel failure, or an evaluation-window misconfiguration.

## Section 1 — Quick checks (first 60 seconds)

Before deep-diving, confirm the basics:

1. Open **Alerts → Active Rules** and confirm the rule is set to **Enabled**, not **Paused** or **Snoozed**.
2. Open **Settings → Integrations** and verify every cloud provider integration shows status **Healthy** (green). A red status means CloudDash cannot read the underlying metrics, so no alert can fire.
3. Open **Settings → Notification Channels** and click **Send Test** on each channel attached to the alert rule. If the test fails, the channel is broken — fix the channel first.

If any of the above is unhealthy, fix it and wait one full evaluation window (default: 5 minutes for Starter, 1 minute for Pro/Enterprise) before re-testing.

## Section 2 — Cause: stale integration credentials

This is the #1 cause of "alerts stopped firing yesterday." When you rotate cloud-provider credentials (AWS access keys, GCP service-account keys, Azure client secrets), CloudDash must be re-authorized. Until you re-link, CloudDash silently fails to fetch metrics, and rules cannot evaluate.

**Symptom**: Alerts that previously fired daily/hourly suddenly stop firing across multiple unrelated rules tied to the same cloud account. The integration page shows status **Unauthorized** or **Permission denied**.

**Fix**: see KB-008 *Re-linking cloud-provider credentials after rotation*. After re-linking, alerts resume on the next evaluation window.

## Section 3 — Cause: paused or modified alert rule

A teammate may have paused or edited the rule.

**Fix**:
1. Open **Alerts → Active Rules** and click the affected rule.
2. Check the **Audit Log** panel for recent edits — every change is timestamped with the user who made it (Pro and Enterprise plans).
3. If paused, click **Resume**. If the threshold or query was changed, revert via **History → Restore version**.

## Section 4 — Cause: notification channel broken

CloudDash supports email, Slack, PagerDuty, Opsgenie, Microsoft Teams, and webhooks. If the channel itself is broken, the alert fires internally but no notification reaches you.

**Fix**:
1. Go to **Settings → Notification Channels**.
2. Click **Send Test** on the channel.
3. If the test fails:
   - **Slack**: re-authorize the Slack workspace integration.
   - **PagerDuty**: regenerate the integration key.
   - **Webhook**: verify the endpoint returns HTTP 2xx within 5 seconds.
   - **Email**: check the recipient address for typos and confirm your domain has not blocklisted `alerts@clouddash.com`.

## Section 5 — Cause: evaluation window misconfiguration

If the alert query window is shorter than your metric ingestion delay, the rule evaluates against incomplete data and may never trip.

**Fix**: Set evaluation window ≥ ingestion latency. Typical defaults:
- AWS CloudWatch metrics: 5-minute lag → use ≥ 10-minute window.
- GCP Cloud Monitoring: 3-minute lag → use ≥ 5-minute window.
- Azure Monitor: 4-minute lag → use ≥ 8-minute window.

## Section 6 — Still not working?

If you have completed all sections above and alerts still are not firing, capture:

1. The **Rule ID** (from the rule URL).
2. The **Trace ID** for the last expected fire time (Pro/Enterprise: visible in **Alerts → Diagnostics**).
3. A screenshot of the **Integrations** page status.

Then contact CloudDash Support with this information for fastest resolution. See KB-019 for how to retrieve audit logs to attach to your support request.
