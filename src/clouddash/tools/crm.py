"""Mock CRM lookup — used by the Billing Agent.

In production this would call Stripe + your customer DB. For the prototype
we read from `data/mock_customers.json`. Used to demonstrate tool-use without
external dependencies.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from clouddash.exceptions import ToolExecutionError
from clouddash.logging_setup import get_logger
from clouddash.settings import get_settings

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def _load_db() -> dict[str, Any]:
    settings = get_settings()
    path = Path(settings.mock_crm_path)
    if not path.exists():
        raise ToolExecutionError(
            f"Mock CRM file not found: {path}",
            context={"path": str(path)},
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ToolExecutionError(
            f"Invalid JSON in mock CRM: {path}",
            context={"path": str(path)},
            cause=exc,
        ) from exc


def lookup_customer(*, customer_id: str | None = None, org_name: str | None = None) -> dict[str, Any] | None:
    """Look up a customer by ID or org name. Returns the full record or None."""
    db = _load_db()
    if customer_id and customer_id in db:
        result = db[customer_id]
        logger.info("crm.lookup_hit", customer_id=customer_id, by="id")
        return result
    if org_name:
        norm = org_name.strip().lower()
        for cust in db.values():
            if cust.get("org_name", "").lower() == norm:
                logger.info("crm.lookup_hit", customer_id=cust["customer_id"], by="org_name")
                return cust
    logger.info("crm.lookup_miss", customer_id=customer_id, org_name=org_name)
    return None


def find_invoice(customer: dict[str, Any], invoice_id: str | None = None, *, period: str | None = None) -> dict[str, Any] | None:
    """Find an invoice in a customer record by id or billing period substring."""
    invoices: list[dict[str, Any]] = customer.get("current_invoices", [])
    if invoice_id:
        for inv in invoices:
            if inv.get("invoice_id") == invoice_id:
                return inv
    if period:
        lower = period.lower()
        for inv in invoices:
            if lower in inv.get("billing_period", "").lower():
                return inv
    return None
