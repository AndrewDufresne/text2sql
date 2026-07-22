"""Phase 3 — Golden Set evaluation harness.

Reads `golden_set.yaml`, POSTs each case to a running langgraph-app, and
prints a pass/fail report.  Exits non-zero if pass-rate is below threshold.

Why a Python harness rather than `promptfoo eval`:
  * No Node.js dep in CI.
  * Direct access to our typed contracts means richer assertions
    (sql_must_contain, tables_used, OPA error_code) without bespoke
    Promptfoo assertion plugins.
  * Promptfoo config is still shipped (`promptfoo.yaml`) for ad-hoc local
    exploration and prompt diff'ing.

Usage:
    python tests/eval/run_eval.py \
        --base-url http://localhost:8080 \
        --golden tests/eval/golden_set.yaml \
        --report tests/eval/report.json

Exit codes:
    0  pass-rate >= threshold
    1  pass-rate <  threshold
    2  configuration / IO error
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import yaml


@dataclass
class CaseResult:
    id: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    status: str = ""
    sql: str | None = None
    error_code: str | None = None
    latency_ms: int = 0
    tables_used: list[str] = field(default_factory=list)
    row_count: int = 0


def _expect_str_set(s: Any) -> set[str]:
    if isinstance(s, list):
        return {str(x).lower() for x in s}
    if isinstance(s, str):
        return {s.lower()}
    return set()


def _check_case(case: dict[str, Any], resp: dict[str, Any]) -> CaseResult:
    expect = case.get("expect", {})
    reasons: list[str] = []
    status = resp.get("status") or ""
    sql = (resp.get("sql") or "").lower()
    err_code = (resp.get("error") or {}).get("code") if resp.get("error") else None
    tables = resp.get("tables_used") or []
    row_count = (resp.get("result") or {}).get("row_count", 0)

    want_status = expect.get("status")
    if want_status and status != want_status:
        reasons.append(f"status: want={want_status} got={status}")

    want_code = expect.get("error_code")
    if want_code and err_code != want_code:
        reasons.append(f"error_code: want={want_code} got={err_code}")
    want_codes = expect.get("error_code_oneof")
    if want_codes and err_code not in want_codes:
        reasons.append(f"error_code: want_oneof={want_codes} got={err_code}")

    for fragment in expect.get("sql_must_contain", []) or []:
        if fragment.lower() not in sql:
            reasons.append(f"sql missing fragment: {fragment!r}")
    for fragment in expect.get("sql_must_not_contain", []) or []:
        if fragment.lower() in sql:
            reasons.append(f"sql has forbidden fragment: {fragment!r}")

    if "row_count" in expect and row_count != expect["row_count"]:
        reasons.append(f"row_count: want={expect['row_count']} got={row_count}")
    if "row_count_min" in expect and row_count < expect["row_count_min"]:
        reasons.append(f"row_count<{expect['row_count_min']} got={row_count}")
    if "row_count_max" in expect and row_count > expect["row_count_max"]:
        reasons.append(f"row_count>{expect['row_count_max']} got={row_count}")

    want_tables = expect.get("tables_used")
    if want_tables is not None and sorted(tables) != sorted(want_tables):
        reasons.append(f"tables_used: want={sorted(want_tables)} got={sorted(tables)}")
    subset = expect.get("tables_used_subset")
    if subset is not None and not set(subset).issubset(set(tables)):
        reasons.append(f"tables_used_subset: want⊇{subset} got={sorted(tables)}")

    return CaseResult(
        id=case["id"],
        passed=not reasons,
        reasons=reasons,
        status=status,
        sql=resp.get("sql"),
        error_code=err_code,
        latency_ms=int(resp.get("latency_ms") or 0),
        tables_used=tables,
        row_count=row_count,
    )


def _post_query(base_url: str, case: dict[str, Any], timeout: float) -> dict[str, Any]:
    body = {
        "trace_id": str(uuid.uuid4()),
        "user": {
            "id": case.get("user_id", "eval@bank"),
            "role": case.get("role", "RM"),
            "business_unit": case.get("business_unit", "CIB-APAC"),
        },
        "question": case["question"],
    }
    r = httpx.post(f"{base_url}/api/v1/query", json=body, timeout=timeout)
    if r.status_code != 200:
        return {
            "status": "error",
            "error": {"code": f"HTTP_{r.status_code}", "message": r.text[:300]},
        }
    return r.json()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default=os.environ.get("LANGGRAPH_URL", "http://localhost:8080"))
    p.add_argument("--golden", default="tests/eval/golden_set.yaml")
    p.add_argument("--report", default="tests/eval/report.json")
    p.add_argument("--timeout", type=float, default=120.0)
    p.add_argument("--threshold", type=float, default=None,
                   help="override pass-rate threshold from YAML")
    args = p.parse_args()

    golden_path = Path(args.golden)
    if not golden_path.exists():
        print(f"[eval] golden set not found: {golden_path}", file=sys.stderr)
        return 2
    spec = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    threshold = args.threshold if args.threshold is not None else float(
        spec.get("threshold_pass_rate", 0.9)
    )
    cases: list[dict[str, Any]] = spec.get("cases", [])

    results: list[CaseResult] = []
    for case in cases:
        try:
            resp = _post_query(args.base_url, case, args.timeout)
        except Exception as e:  # noqa: BLE001
            results.append(CaseResult(id=case["id"], passed=False,
                                      reasons=[f"http_error: {e}"]))
            continue
        results.append(_check_case(case, resp))

    passed = sum(1 for r in results if r.passed)
    total = len(results) or 1
    rate = passed / total

    print(f"\n=== Golden Set Eval — {passed}/{total} pass ({rate:.1%}) "
          f"threshold={threshold:.0%} ===\n")
    for r in results:
        marker = "PASS" if r.passed else "FAIL"
        line = f"  [{marker}] {r.id}  status={r.status} sql_chars={len(r.sql or '')}"
        if not r.passed:
            line += f"  reasons={r.reasons}"
        print(line)

    report = {
        "passed": passed,
        "total": total,
        "pass_rate": rate,
        "threshold": threshold,
        "cases": [r.__dict__ for r in results],
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n[eval] report: {args.report}")

    return 0 if rate >= threshold else 1


if __name__ == "__main__":
    sys.exit(main())
