"""FastAPI app — JSON API + HTMX UI.

Import path for uvicorn / Render:

    uvicorn clouddash.api.app:app
"""

from clouddash.api.app import app

__all__ = ["app"]
