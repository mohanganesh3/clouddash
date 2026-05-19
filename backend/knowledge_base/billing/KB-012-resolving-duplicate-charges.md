---
id: KB-012
title: Resolving Duplicate Charges
category: billing
tags: [billing, charges, refund, payment, dispute]
last_updated: 2026-04-18
applies_to: [Free, Starter, Pro, Enterprise]
---

# Resolving Duplicate Charges

If you see two or more charges from CloudDash for the same billing period, this guide explains how to verify whether the charges are legitimate, and what to do if they are not.

## Section 1 — Common reasons you may see two charges

Before assuming it is a duplicate, check whether one of the following applies:

1. **Plan upgrade mid-cycle**: When you upgrade (e.g. Pro → Enterprise) mid-billing-cycle, CloudDash issues a prorated charge for the remainder of the current cycle, on top of your normal monthly charge. These appear as two separate line items but are NOT duplicates. See KB-010 for how upgrade billing works.
2. **Multiple workspaces under the same payment method**: If your payment method is attached to two CloudDash workspaces (e.g. Acme-Production and Acme-Staging), each will charge independently.
3. **Failed retry success**: If a payment failed and the retry succeeded, you may see one declined charge and one successful charge for the same period. The declined charge is reversed automatically by your card issuer within 3–5 business days.
4. **Currency conversion display**: International cards may show two pending entries — one in USD (the actual charge) and one in your local currency (a temporary authorization that drops off in 1–7 days).

## Section 2 — How to verify

1. Open **Settings → Billing → Invoice history**.
2. Compare each charge on your bank/card statement to a CloudDash invoice line item.
3. If every charge maps to exactly one invoice, the billing is correct. If you see a charge with no matching invoice, proceed to Section 3.

## Section 3 — If the charges are genuinely duplicated

CloudDash policy: **any genuinely duplicated charge is refunded in full, automatically, within one business day** of confirmation.

To request the refund:

1. Open **Settings → Billing → Dispute a charge**.
2. Select the duplicated charge.
3. Enter your reason (e.g. "Two identical charges for April invoice INV-2026-04-1234").
4. Submit.

CloudDash Billing reviews the dispute within 4 business hours during weekdays. On confirmation, the duplicate is refunded to the original payment method. Refunds typically appear on your statement within 5–10 business days, depending on your card issuer.

## Section 4 — Refund authority

The Billing Agent has authority to refund:

- Single duplicate charges up to **$1,000 USD** automatically.
- Plan-mismatch refunds (e.g. you were billed Enterprise but only on Pro features) automatically.

The Billing Agent does NOT have authority to refund:

- Disputes over **$1,000 USD** — these escalate to a Billing Manager.
- Refunds older than the most recent two billing cycles — these require manager review per our refund policy (KB-011).
- Partial-month refunds when downgrading mid-cycle (these are credited toward the next invoice, not refunded — see KB-011 § 4).

If your dispute falls into one of these categories, the system will automatically escalate to a human Billing Manager. You will receive a confirmation email within 1 business hour, and a manager will reach out within 1 business day.

## Section 5 — Urgent situations

If the duplicate charge is causing a hardship (overdraft, business cash-flow issue), mention this when submitting the dispute. Urgent disputes are routed to the Billing Manager queue with **priority high** and typically receive a response within 2 business hours during weekdays.

You may also request to **speak with a manager directly** — see Section 6.

## Section 6 — Speaking to a billing manager

You can request manager escalation at any time:

1. Reply to your most recent invoice email with "I want to speak to a manager about [INV-XXXX]".
2. Or, in the support chat, type "Escalate to billing manager".

The system packages your conversation history, the disputed invoice, and your sentiment + urgency context into a structured escalation ticket and routes it to a human manager. You will get the ticket number immediately and a manager response within 1 business day.

## Section 7 — Related articles

- KB-011: Refund policy
- KB-013: Invoice format and how to read it
- KB-010: How to upgrade your plan
