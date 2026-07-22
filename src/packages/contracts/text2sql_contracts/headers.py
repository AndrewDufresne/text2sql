"""Common HTTP headers required on every cross-service call (see io-contracts §0.1)."""

from __future__ import annotations

from pydantic import BaseModel, Field

REQUIRED_HEADERS: tuple[str, ...] = (
    "X-Trace-Id",
    "X-User-Id",
    "X-User-Role",
    "X-Request-Id",
    "X-App-Version",
)


class TraceHeaders(BaseModel):
    """Typed view of the cross-cutting trace headers."""

    trace_id: str = Field(..., alias="X-Trace-Id")
    user_id: str = Field(..., alias="X-User-Id")
    user_role: str = Field(..., alias="X-User-Role")
    request_id: str = Field(..., alias="X-Request-Id")
    app_version: str = Field(..., alias="X-App-Version")

    model_config = {"populate_by_name": True}

    def as_dict(self) -> dict[str, str]:
        return {
            "X-Trace-Id": self.trace_id,
            "X-User-Id": self.user_id,
            "X-User-Role": self.user_role,
            "X-Request-Id": self.request_id,
            "X-App-Version": self.app_version,
        }
