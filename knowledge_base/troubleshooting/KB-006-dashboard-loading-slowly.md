---
id: KB-006
title: Troubleshooting — Dashboard Loading Slowly
category: troubleshooting
tags: [dashboards, performance, troubleshooting]
last_updated: 2026-04-20
applies_to: [Free, Starter, Pro, Enterprise]
---

# Troubleshooting — Dashboard Loading Slowly

If your CloudDash dashboards take more than 5–10 seconds to render, this guide identifies the most common causes and the steps to fix them.

## Section 1 — Establish a baseline

Before optimizing, measure:

1. Open the dashboard in a private/incognito browser window (rules out browser extension overhead).
2. Open the browser developer tools' **Network** tab.
3. Reload. Note the time-to-first-byte (TTFB) and total render time.

Healthy ranges:
- TTFB: < 500 ms
- Total render: < 3 s for ≤ 12 panels, < 8 s for 12–30 panels.

If your numbers significantly exceed these, continue.

## Section 2 — Cause: too many panels per dashboard

Dashboards with 30+ panels each running independent queries are the most common cause of slowness. CloudDash parallelizes panel queries up to a per-user concurrency limit, but past ~30 panels the experience degrades.

**Fix**: Split into multiple linked dashboards. Use **Dashboard → Split** which suggests a logical split based on panel categories.

## Section 3 — Cause: long time-range queries on high-cardinality data

A single panel querying 30 days of per-second data across 1000 hosts runs into millions of data points.

**Fix**: Reduce the time range or aggregate at a higher resolution. Most dashboards work fine with 1-minute resolution for 24-hour views, 5-minute for 7-day, and 1-hour for 30-day.

## Section 4 — Cause: integration backpressure

If a recent surge in metric ingestion (e.g. you scaled out from 50 to 5000 EC2 instances overnight) is overwhelming your plan's ingestion quota, queries lag while the indexer catches up.

**Fix**: Check **Settings → Plan usage** for your ingestion-rate utilization. If you are at > 80% sustained, upgrade your plan or reduce metric scope.

## Section 5 — Cause: browser

Older browsers (IE, very old Safari) are not supported. Chrome, Firefox, Safari 16+, and Edge are tested. If your browser is current and the issue persists, try:

- Clear cache for `app.clouddash.com`.
- Disable browser extensions that intercept XHRs (uBlock with custom rules, etc.).

## Section 6 — Still slow?

Capture the dashboard URL, the Trace ID from **Help → Diagnostics → Last load**, and your browser version. Contact support — slow-dashboard tickets get a 1-business-hour response on Pro/Enterprise.

## Section 7 — Related articles

- KB-005: Alerts not firing
- KB-019: Viewing audit logs
