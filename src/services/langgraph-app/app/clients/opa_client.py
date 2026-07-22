"""OPA HTTP client.

  POST {opa}/v1/data/{decision_path}   body: {"input": {...}}
  -> {"result": {"allow": bool, "reasons": [...], "matched_policy": str}}

Local fallback enforces the same allowlist when OPA is offline so unit tests
don't need the container.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)

# Mirror of `config/opa/policies/text2sql.rego`. Keep in sync.
# Phase 5: extended domain. Per-role allowlist follows least-privilege:
#   * client_contact (PII) and rm_user (PII) -> Compliance + Admin only.
#   * covenant + collateral + rating_history (credit-risk) -> Risk + Compliance + Admin.
#   * Ops gets only operational tables (no exposure / no risk metrics).
_CORE_RO = {"client", "account", "country_ref", "industry_ref", "fx_rate"}
_FACTS   = {"transaction", "daily_balance"}
_CREDIT  = {"exposure", "covenant", "collateral", "rating_history"}
_PII     = {"client_contact", "rm_user"}
_ROLE_TABLES: dict[str, set[str]] = {
    "RM":         _CORE_RO | _FACTS | _CREDIT,
    "Risk":       _CORE_RO | _FACTS | _CREDIT,
    "Compliance": _CORE_RO | _FACTS | _CREDIT | _PII,
    "Ops":        _CORE_RO | _FACTS,
    "Finance":    _CORE_RO | _FACTS | _CREDIT,
    "Admin":      _CORE_RO | _FACTS | _CREDIT | _PII,
}
_ALLOWED_OPS: set[str] = {"SELECT"}


def _local_decision(input_: dict[str, Any]) -> dict[str, Any]:
    role = input_["user"]["role"]
    user_id = input_["user"].get("id", "unknown")
    tables = set(input_.get("tables", []))
    ops = set(input_.get("ops", []))
    if role not in _ROLE_TABLES:
        return dict(allow=False, reasons=[f"unknown_role:{role}"],
                    matched_policy="role_unknown")
    bad_tbl = tables - _ROLE_TABLES[role]
    if bad_tbl:
        return dict(allow=False,
                    reasons=[f"table_not_allowed_for_role:{role}:{sorted(bad_tbl)}"],
                    matched_policy=f"role:{role}")
    bad_op = ops - _ALLOWED_OPS
    if bad_op:
        return dict(allow=False, reasons=[f"op_not_allowed:{sorted(bad_op)}"],
                    matched_policy="ops_allowlist")
    obligations: dict[str, str] = {}
    if role == "RM":
        obligations["row_filter"] = f"client.rm_owner = '{user_id}'"
    return dict(allow=True, reasons=[], matched_policy=f"role:{role}",
                obligations=obligations)


async def evaluate(input_: dict[str, Any]) -> dict[str, Any]:
    s = get_settings()
    if not s.opa_enabled:
        return _local_decision(input_)
    url = f"{s.opa_url}/v1/data/{s.opa_decision_path}"
    try:
        async with httpx.AsyncClient(timeout=3.0) as cx:
            r = await cx.post(url, json={"input": input_})
            r.raise_for_status()
            data = r.json()
            result = data.get("result")
            if not isinstance(result, dict) or "allow" not in result:
                _log.error("opa_unexpected_response_fail_closed", body=data)
                return _opa_unreachable_deny("unexpected_response")
            return result
    except Exception as e:  # noqa: BLE001
        _log.error("opa_call_failed_fail_closed", error=str(e))
        return _opa_unreachable_deny("connection_failed")


def _opa_unreachable_deny(reason: str) -> dict[str, Any]:
    """Fail-closed: if OPA is unreachable, deny the request.

    Rationale: the Architecture.md hard constraint is fail-closed on authz.
    A silent fallback to a Python mirror undermines OPA's role as the single
    policy-enforcement point.  The Python mirror (_local_decision) is now
    used ONLY when ``opa_enabled=False`` (unit tests / local dev without
    the OPA container).
    """
    return dict(
        allow=False,
        reasons=[f"opa_unreachable:{reason}"],
        matched_policy="fail_closed",
    )
