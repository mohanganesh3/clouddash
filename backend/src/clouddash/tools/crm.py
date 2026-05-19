"""Mock CRM tool — simulates real account lookups.

In production this would call our internal API or Salesforce.
For the demo it reads from data/mock_customers.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from clouddash.settings import get_settings


def _load_customers() -> dict[str, Any]:
    path = Path(get_settings().mock_crm_path)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        # support both {customers: [...]} and flat list formats
        if isinstance(data, list):
            return {c["customer_id"]: c for c in data if "customer_id" in c}
        if isinstance(data, dict) and "customers" in data:
            return {c["customer_id"]: c for c in data["customers"]}
        return data
    except Exception:
        return {}


@tool
def crm_lookup(customer_id: str) -> dict[str, Any]:
    """Look up a customer's account details, plan, and billing status by customer ID."""
    customers = _load_customers()
    rec = customers.get(customer_id)
    if not rec:
        return {"error": f"unknown customer: {customer_id}"}
    return {
        "customer_id": rec.get("customer_id"),
        "org_name": rec.get("org_name", ""),
        "plan": rec.get("plan", "free"),
        "email": rec.get("email", ""),
        "billing_status": rec.get("billing_status", "active"),
        "invoices": rec.get("invoices", [])[-3:],  # last 3 only
    }


@tool
def list_plans() -> list[dict[str, Any]]:
    """List all available CloudDash subscription plans with pricing and features."""
    return [
        {"plan": "free", "price_monthly": 0, "agents": 2, "integrations": 1, "alerts": 10},
        {"plan": "starter", "price_monthly": 49, "agents": 5, "integrations": 5, "alerts": 100},
        {"plan": "pro", "price_monthly": 149, "agents": 20, "integrations": 20, "alerts": 1000, "sso": True},
        {"plan": "enterprise", "price_monthly": "custom", "agents": "unlimited", "sso": True, "rbac": True, "sla": "99.9%"},
    ]
