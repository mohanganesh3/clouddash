---
id: KB-002
title: What Cloud Providers Does CloudDash Support?
category: faqs
tags: [integrations, aws, gcp, azure, cloud-providers, faq]
last_updated: 2026-05-01
applies_to: [Free, Starter, Pro, Enterprise]
---

# What Cloud Providers Does CloudDash Support?

CloudDash provides native first-party integrations for the three major hyperscale cloud providers, plus Kubernetes and selected DevOps tooling. Coverage varies by plan tier.

## Section 1 — Supported providers (native integrations)

| Provider | Status | Min plan |
|---|---|---|
| **Amazon Web Services (AWS)** | Generally available | Free |
| **Google Cloud Platform (GCP)** | Generally available | Starter |
| **Microsoft Azure** | Generally available | Starter |
| **Kubernetes** (any conformant cluster — EKS, GKE, AKS, k3s, on-prem) | Generally available | Starter |

For each provider we ingest:

- Native metrics (CloudWatch / Cloud Monitoring / Azure Monitor / Prometheus).
- Resource inventory (EC2, GCE, Azure VM, K8s pods/services).
- Cost data (Cost Explorer, GCP Billing, Azure Cost Management).
- Logs (CloudWatch Logs, Cloud Logging, Azure Log Analytics) — Pro and above only.

## Section 2 — Notification and DevOps integrations

CloudDash routes alerts and notifications via:

- Slack
- Microsoft Teams
- PagerDuty
- Opsgenie
- Email (SMTP)
- Webhook (any HTTP endpoint)

These are configured under **Settings → Notification Channels**.

## Section 3 — Multi-cloud monitoring on a single dashboard

Pro and Enterprise plans support cross-cloud queries. You can build a dashboard panel that joins, for example, AWS EC2 CPU usage with Azure VM CPU usage in a single chart.

## Section 4 — Connecting a new provider

1. Open **Settings → Integrations → Connect**.
2. Choose your provider.
3. Follow the IAM / service-account setup wizard. For AWS, see KB-007. For SSO, see KB-017.

## Section 5 — Providers we do NOT currently support

CloudDash does not currently ingest from third-party APM/monitoring vendors as a *source*. If you are using one of these tools and considering migrating to CloudDash, our migration team can help. Email `migrations@clouddash.com`.

We frequently get asked about specific third-party tools — our public roadmap is at `clouddash.com/roadmap`. To file a feature request for a new integration, contact support and ask to file one. Feature requests with multiple customer signals are prioritized for the next quarterly roadmap review.

## Section 6 — Related articles

- KB-007: AWS CloudWatch integration failing
- KB-008: Re-linking AWS credentials
- KB-014: API authentication for programmatic integration setup
