from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from langchain_core.tools import tool


_REQUESTS: list[dict[str, Any]] = []


@tool
def file_feature_request(
    customer_id: str,
    feature_summary: str,
    use_case: str,
) -> dict[str, Any]:
    """File a product feature request on behalf of a customer when the KB has no answer."""
    req_id = f"FR-{uuid.uuid4().hex[:6].upper()}"
    _REQUESTS.append({
        "request_id": req_id,
        "customer_id": customer_id,
        "feature_summary": feature_summary,
        "use_case": use_case,
        "status": "submitted",
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
    })
    return {
        "request_id": req_id,
        "status": "submitted",
        "message": f"Feature request {req_id} submitted. Our product team reviews requests monthly.",
    }
