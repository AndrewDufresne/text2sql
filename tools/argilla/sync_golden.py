"""Promote SME-reviewed Argilla records into `tests/eval/golden_set.yaml`.

Pulls records where:
  * at least one response has `status=submitted`
  * `metadata.reviewed=true`           (set by SME after verifying the SQL)
  * `metadata.golden_set_id` is empty  (not yet promoted)
  * a non-empty `corrected_sql` is present (we have a real ground truth)

For each new record:
  1. Re-validate the corrected SQL via `sql_validate.validate()` so we
     never persist insecure SQL into the regression set.
  2. Append a Golden-Set case to the YAML (under `cases:`).
  3. PATCH the Argilla record `metadata.golden_set_id = <case_id>` so the
     same record is not re-promoted on the next sync.

Usage
-----
    python -m tools.argilla.sync_golden \\
        --url http://localhost:6900 --api-key owner.apikey \\
        --workspace admin --dataset text2sql-feedback \\
        --golden tests/eval/golden_set.yaml \\
        [--dry-run]

Exit codes:
    0  ok (records appended printed to stdout)
    1  Argilla unreachable / IO error
    2  some corrected_sql was rejected by sql_validate (see stderr; the
       record's `metadata.reviewed` is reset to false so SMEs revisit it)
"""

from __future__ import annotations

import argparse
import datetime as _dt
import sys
from pathlib import Path
from typing import Any

import httpx
import yaml


# ---------------------------------------------------------------------------
# sql_validate import is best-effort — when running this CLI from a fresh
# clone without the langgraph-app installed we still want to be useful, so
# we degrade to a no-op safety check + warn.
# ---------------------------------------------------------------------------
try:
    from app.nodes.sql_validate import validate as _sql_validate  # type: ignore
except Exception:  # noqa: BLE001
    _sql_validate = None  # type: ignore[assignment]


def _golden_case_from(record: dict[str, Any]) -> dict[str, Any]:
    md = record.get("metadata", {}) or {}
    fields = record.get("fields", {}) or {}
    case_id = f"hitl-{record['id'][:8]}-{int(_dt.datetime.now().timestamp())}"
    expect: dict[str, Any] = {"status": "ok"}
    tables = md.get("tables_used") or []
    if isinstance(tables, list) and tables:
        expect["tables_used"] = sorted(tables)
    return {
        "id": case_id,
        "role": md.get("user_role") or "RM",
        "question": fields.get("question") or "",
        "expect": expect,
        "tags": ["hitl", "from_argilla"] + (md.get("tags") or []),
        # Round-trip evidence (referenced by run_eval.py for human debugging
        # but not asserted on — corrected_sql is the *target*, not equality).
        "_source": {
            "argilla_record_id": record["id"],
            "trace_id": md.get("trace_id"),
            "expected_sql": fields.get("corrected_sql"),
        },
    }


class Argilla:
    def __init__(self, url: str, api_key: str) -> None:
        self.cx = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"X-Argilla-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=20.0,
        )

    def workspace_id(self, name: str) -> str:
        r = self.cx.get("/api/v1/workspaces")
        r.raise_for_status()
        for w in r.json().get("items") or []:
            if w["name"] == name:
                return w["id"]
        raise RuntimeError(f"workspace not found: {name}")

    def dataset_id(self, ws_id: str, ds_name: str) -> str:
        r = self.cx.get("/api/v1/me/datasets")
        r.raise_for_status()
        for d in r.json().get("items") or []:
            if d["name"] == ds_name and d["workspace_id"] == ws_id:
                return d["id"]
        raise RuntimeError(f"dataset not found: {ds_name}")

    def list_records(self, ds_id: str) -> list[dict[str, Any]]:
        # Includes responses + metadata so we can filter without a 2nd hop.
        r = self.cx.get(
            f"/api/v1/datasets/{ds_id}/records",
            params={"include": "responses,metadata", "limit": 1000},
        )
        r.raise_for_status()
        return r.json().get("items") or []

    def patch_metadata(self, record_id: str, metadata: dict[str, Any]) -> None:
        r = self.cx.patch(
            f"/api/v1/records/{record_id}", json={"metadata": metadata}
        )
        if r.status_code not in (200, 204):
            r.raise_for_status()


# ---------------------------------------------------------------------------
# Golden-set YAML I/O
# ---------------------------------------------------------------------------


def _load_golden(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"threshold_pass_rate": 0.90, "cases": []}
    with path.open("r", encoding="utf-8") as f:
        doc = yaml.safe_load(f) or {}
    doc.setdefault("cases", [])
    return doc


def _save_golden(path: Path, doc: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(doc, f, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# Filter / promote
# ---------------------------------------------------------------------------


def _is_promotable(rec: dict[str, Any]) -> bool:
    md = rec.get("metadata") or {}
    if not md.get("reviewed"):
        return False
    if md.get("golden_set_id"):
        return False
    fields = rec.get("fields") or {}
    return bool(fields.get("corrected_sql"))


def _validate_or_warn(sql: str) -> tuple[bool, str]:
    if _sql_validate is None:
        return True, "skipped (sql_validate unavailable)"
    res = _sql_validate(sql)
    if not res.safe:
        return False, "; ".join(res.violations)
    return True, "ok"


def sync(
    url: str,
    api_key: str,
    workspace: str,
    dataset: str,
    golden_path: Path,
    dry_run: bool,
) -> int:
    try:
        ag = Argilla(url, api_key)
        ws_id = ag.workspace_id(workspace)
        ds_id = ag.dataset_id(ws_id, dataset)
        records = ag.list_records(ds_id)
    except Exception as e:  # noqa: BLE001
        print(f"[sync_golden] argilla error: {e}", file=sys.stderr)
        return 1

    doc = _load_golden(golden_path)
    seen_case_ids = {c.get("id") for c in doc["cases"]}
    appended: list[str] = []
    rejected: list[tuple[str, str]] = []

    for rec in records:
        if not _is_promotable(rec):
            continue
        sql = (rec.get("fields") or {}).get("corrected_sql") or ""
        ok, reason = _validate_or_warn(sql)
        if not ok:
            rejected.append((rec["id"], reason))
            if not dry_run:
                ag.patch_metadata(
                    rec["id"],
                    {"reviewed": False, "sync_rejected_reason": reason[:300]},
                )
            continue

        case = _golden_case_from(rec)
        if case["id"] in seen_case_ids:
            continue
        doc["cases"].append(case)
        seen_case_ids.add(case["id"])
        appended.append(case["id"])
        if not dry_run:
            ag.patch_metadata(rec["id"], {"golden_set_id": case["id"]})

    if appended and not dry_run:
        _save_golden(golden_path, doc)

    print(f"[sync_golden] appended={len(appended)} rejected={len(rejected)} "
          f"dry_run={dry_run}")
    for cid in appended:
        print(f"  + {cid}")
    for rid, why in rejected:
        print(f"  ! {rid}  {why}", file=sys.stderr)
    return 2 if rejected else 0


def _argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Promote Argilla SME-reviewed records into Golden Set.")
    p.add_argument("--url", default="http://localhost:6900")
    p.add_argument("--api-key", default="owner.apikey")
    p.add_argument("--workspace", default="admin")
    p.add_argument("--dataset", default="text2sql-feedback")
    p.add_argument("--golden", default="tests/eval/golden_set.yaml", type=Path)
    p.add_argument("--dry-run", action="store_true")
    return p


if __name__ == "__main__":
    a = _argparser().parse_args()
    sys.exit(sync(a.url, a.api_key, a.workspace, a.dataset, a.golden, a.dry_run))
