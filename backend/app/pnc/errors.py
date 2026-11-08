"""Domain errors mapped to HTTP statuses by `app.pnc.api.deps.run`."""
from __future__ import annotations


class AccessDenied(Exception):
    """A business-rule denial (consent, limits). Carries a machine-readable reason. Mapped to HTTP 403."""

    def __init__(self, reason: str, detail: str | None = None):
        self.reason, self.detail = reason, detail
        super().__init__(reason)


class NotFound(Exception):
    """The requested object does not exist or is not visible to the caller. Mapped to HTTP 404."""


class Unavailable(Exception):
    """A dependency the request needs is not ready (e.g. an untrained model). Mapped to HTTP 503."""
