---
id: KB-013
title: CloudDash Invoice Format and How to Read It
category: billing
tags: [billing, invoice, faq]
last_updated: 2026-03-15
applies_to: [Starter, Pro, Enterprise]
---

# CloudDash Invoice Format and How to Read It

CloudDash invoices are generated on the 1st of each month for the prior month's usage and current-month subscription. This article walks through every line item.

## Section 1 — Where to find your invoices

1. **Settings → Billing → Invoice history**.
2. Click any invoice to download as PDF.
3. All invoices are also emailed to your billing contact (configured under **Settings → Billing → Contacts**).

Invoices are retained for 7 years on Pro and Enterprise; 3 years on Starter.

## Section 2 — Invoice line items

A typical Pro invoice contains:

| Line | What it is |
|---|---|
| **Subscription — Pro plan** | $149.00 monthly fee for the upcoming month |
| **Additional users** | $10/user × N for users beyond the 25 included |
| **Mid-cycle plan upgrade** | Prorated difference if you upgraded mid-cycle (see KB-010 § 4) |
| **Ingestion overage** | $0.05 per million metric data points beyond plan quota |
| **Log storage overage** | $0.10 per GB-month beyond plan quota (Pro and above) |
| **Tax** | Sales tax / VAT / GST per your billing address |
| **Credits applied** | Goodwill credits, prior-month overpayment, downgrade credits |

## Section 3 — Reading the line "Subscription — Pro plan ($149.00)"

Subscriptions are billed **in advance**. The invoice generated on May 1 charges you for the *coming* month of May. If you cancel mid-May, you are NOT refunded the unused portion (see KB-011 § 4).

## Section 4 — Reading mid-cycle upgrade lines

If you upgraded from Pro to Enterprise on April 16 and your billing cycle is the 1st of the month, your May 1 invoice will contain:

- **Subscription — Enterprise plan** ($999.00) — for May, billed in advance.
- **Mid-cycle plan upgrade — Apr 16 to Apr 30** (prorated $425.00 in the example from KB-010 § 4) — covering the upgraded portion of April.

This is two line items, NOT a duplicate charge. See KB-012 if you suspect a real duplicate.

## Section 5 — Tax IDs and tax-exempt status

If your organization is tax-exempt or requires a different VAT/GST treatment:

1. Email `billing@clouddash.com` from your registered billing contact.
2. Attach your tax-exempt certificate or VAT ID.
3. Future invoices will reflect the change. (Past invoices cannot be amended.)

## Section 6 — Currency

CloudDash bills in USD by default. Enterprise customers can negotiate billing in EUR, GBP, INR, AUD, or JPY in their contract. All payment processing is via Stripe; international cards may incur a 1–3% currency conversion fee charged by your card issuer (CloudDash does not charge a markup on currency conversion).

## Section 7 — Related articles

- KB-010: How to upgrade your plan
- KB-011: Refund policy
- KB-012: Resolving duplicate charges
