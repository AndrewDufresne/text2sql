"""Bootstrap the Argilla workspace + `text2sql_feedback` dataset.

Idempotent: GET first, only POST if missing.  Safe to run on every
deploy.  Implements the schema declared in `docs/layers/L6-hitl.md` §2.1
so the LangGraph `argilla_client` writes never 404 on missing fields.

Usage
-----
    python -m tools.argilla.bootstrap \\
        --url     http://localhost:6900 \\
        --api-key owner.apikey \\
        --workspace admin \\
        --dataset text2sql-feedback \\
        --vector-dim 384       # match TEI / question embedding

Exit codes:
    0 — workspace + dataset ready
    1 — Argilla unreachable / auth failed
    2 — schema mismatch the script can't fix in-place
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import httpx


# ---------------------------------------------------------------------------
# Schema: must mirror `docs/layers/L6-hitl.md` §2.1 and what argilla_client
# writes.  Adding a column? Update both this script AND argilla_client._to_record.
# ---------------------------------------------------------------------------

FIELDS: list[dict[str, Any]] = [
    {"name": "question", "title": "Question", "settings": {"type": "text", "use_markdown": False}, "required": True},
    {"name": "sql", "title": "Generated SQL", "settings": {"type": "text", "use_markdown": True}, "required": False},
    {"name": "corrected_sql", "title": "Corrected SQL", "settings": {"type": "text", "use_markdown": True}, "required": False},
    {"name": "result_preview", "title": "Result preview", "settings": {"type": "text", "use_markdown": True}, "required": False},
    {"name": "explanation", "title": "NL explanation", "settings": {"type": "text", "use_markdown": True}, "required": False},
    {"name": "comment", "title": "User comment", "settings": {"type": "text", "use_markdown": False}, "required": False},
]

QUESTIONS: list[dict[str, Any]] = [
    {
        "name": "thumb",
        "title": "Was the answer correct?",
        "required": True,
        "settings": {
            "type": "label_selection",
            "options": [
                {"value": "up", "text": "👍 Correct"},
                {"value": "down", "text": "👎 Incorrect"},
            ],
        },
    },
    {
        "name": "corrected_sql",
        "title": "Corrected SQL (if any)",
        "required": False,
        "settings": {"type": "text", "use_markdown": True},
    },
    {
        "name": "failure_mode",
        "title": "Failure mode (if 👎)",
        "required": False,
        "settings": {
            "type": "label_selection",
            "options": [
                {"value": "wrong_metric", "text": "Wrong metric"},
                {"value": "wrong_join", "text": "Wrong join"},
                {"value": "wrong_filter", "text": "Wrong filter"},
                {"value": "hallucination", "text": "Hallucination"},
                {"value": "perf", "text": "Performance"},
                {"value": "other", "text": "Other"},
            ],
        },
    },
]

METADATA_PROPERTIES: list[dict[str, Any]] = [
    # ``title`` is required by Argilla 1.29; in 2.x it is optional but accepted.
    {"name": "trace_id",       "title": "Trace ID",       "settings": {"type": "terms"}},
    {"name": "user_id",        "title": "User ID",        "settings": {"type": "terms"}},
    {"name": "user_role",      "title": "User role",      "settings": {"type": "terms"}},
    {"name": "business_unit",  "title": "Business unit",  "settings": {"type": "terms"}},
    {"name": "rating",         "title": "Rating",         "settings": {"type": "terms"}},
    {"name": "failure_mode",   "title": "Failure mode",   "settings": {"type": "terms"}},
    {"name": "model",          "title": "Model",          "settings": {"type": "terms"}},
    {"name": "prompt_version", "title": "Prompt version", "settings": {"type": "terms"}},
    {"name": "tables_used",    "title": "Tables used",    "settings": {"type": "terms"}},
    {"name": "metrics_used",   "title": "Metrics used",   "settings": {"type": "terms"}},
    {"name": "tags",           "title": "Tags",           "settings": {"type": "terms"}},
    {"name": "reviewed",       "title": "Reviewed",       "settings": {"type": "terms"}},
    {"name": "cost_usd",       "title": "Cost (USD)",     "settings": {"type": "float",   "min": 0.0}},
    {"name": "latency_ms",     "title": "Latency (ms)",   "settings": {"type": "integer", "min": 0}},
]


def _vector_settings(dim: int) -> list[dict[str, Any]]:
    return [{"name": "question", "title": "Question embedding", "dimensions": dim}]


# ---------------------------------------------------------------------------
# Thin Argilla v2 HTTP client (one tool, no SDK dep — keeps install lean).
# ---------------------------------------------------------------------------


class Argilla:
    def __init__(self, url: str, api_key: str) -> None:
        self.cx = httpx.Client(
            base_url=url.rstrip("/"),
            headers={"X-Argilla-Api-Key": api_key, "Content-Type": "application/json"},
            timeout=20.0,
        )

    # readiness ------------------------------------------------------------
    def wait_ready(self, timeout_s: float = 180.0, interval_s: float = 3.0) -> None:
        """Poll /api/_status + /api/v1/me until both 200.

        argilla-quickstart bundles ES + PG + server in one image; on cold
        boot the HTTP port is open well before ES finishes warm-up, so a
        naive call yields ``Server disconnected without sending a response``.
        """
        deadline = time.monotonic() + timeout_s
        last_err: str = ""
        while time.monotonic() < deadline:
            try:
                s = self.cx.get("/api/_status")
                if s.status_code == 200:
                    m = self.cx.get("/api/v1/me")
                    if m.status_code == 200:
                        return
                    last_err = f"/api/v1/me HTTP {m.status_code}"
                else:
                    last_err = f"/api/_status HTTP {s.status_code}"
            except httpx.HTTPError as e:
                last_err = str(e) or e.__class__.__name__
            time.sleep(interval_s)
        raise httpx.HTTPError(f"Argilla not ready after {timeout_s:.0f}s: {last_err}")

    # workspaces -----------------------------------------------------------
    def get_workspace(self, name: str) -> dict[str, Any] | None:
        # Use /me/workspaces — the only listing endpoint available in BOTH
        # Argilla 1.29 (FeedbackDataset era) and 2.x.  ``GET /api/v1/workspaces``
        # returns 405 on 1.29 (only POST is wired there).
        r = self.cx.get("/api/v1/me/workspaces")
        r.raise_for_status()
        for ws in (r.json().get("items") or []):
            if ws.get("name") == name:
                return ws
        return None

    def ensure_workspace(self, name: str) -> dict[str, Any]:
        ws = self.get_workspace(name)
        if ws:
            return ws
        r = self.cx.post("/api/v1/workspaces", json={"name": name})
        r.raise_for_status()
        return r.json()

    # datasets -------------------------------------------------------------
    def get_dataset(self, ws_id: str, name: str) -> dict[str, Any] | None:
        r = self.cx.get("/api/v1/me/datasets")
        r.raise_for_status()
        for ds in (r.json().get("items") or []):
            if ds.get("name") == name and ds.get("workspace_id") == ws_id:
                return ds
        return None

    def create_dataset(self, ws_id: str, name: str) -> dict[str, Any]:
        r = self.cx.post(
            "/api/v1/datasets",
            json={"name": name, "workspace_id": ws_id, "guidelines": "text2sql HITL feedback"},
        )
        r.raise_for_status()
        return r.json()

    def add_field(self, ds_id: str, body: dict[str, Any]) -> None:
        r = self.cx.post(f"/api/v1/datasets/{ds_id}/fields", json=body)
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()

    def add_question(self, ds_id: str, body: dict[str, Any]) -> None:
        r = self.cx.post(f"/api/v1/datasets/{ds_id}/questions", json=body)
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()

    def add_metadata(self, ds_id: str, body: dict[str, Any]) -> None:
        r = self.cx.post(f"/api/v1/datasets/{ds_id}/metadata-properties", json=body)
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()

    def add_vector(self, ds_id: str, body: dict[str, Any]) -> None:
        r = self.cx.post(f"/api/v1/datasets/{ds_id}/vectors-settings", json=body)
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()

    def publish(self, ds_id: str) -> None:
        r = self.cx.put(f"/api/v1/datasets/{ds_id}/publish")
        # Already published (409) is a success state for our idempotency.
        if r.status_code not in (200, 204, 409):
            r.raise_for_status()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def bootstrap(
    url: str,
    api_key: str,
    workspace: str,
    dataset: str,
    vector_dim: int,
) -> int:
    try:
        ag = Argilla(url, api_key)
    except Exception as e:
        print(f"[argilla-bootstrap] cannot init client: {e}", file=sys.stderr)
        return 1

    try:
        ag.wait_ready()
        print("[argilla-bootstrap] server ready")
    except httpx.HTTPError as e:
        print(f"[argilla-bootstrap] server not ready: {e}", file=sys.stderr)
        return 1

    try:
        ws = ag.ensure_workspace(workspace)
        print(f"[argilla-bootstrap] workspace ok: {workspace} (id={ws['id']})")
    except httpx.HTTPError as e:
        print(f"[argilla-bootstrap] workspace ensure failed: {e}", file=sys.stderr)
        return 1

    ds = ag.get_dataset(ws["id"], dataset)
    if ds is None:
        ds = ag.create_dataset(ws["id"], dataset)
        print(f"[argilla-bootstrap] dataset created: {dataset} (id={ds['id']})")
    else:
        print(f"[argilla-bootstrap] dataset exists: {dataset} (id={ds['id']})")

    if ds.get("status") == "ready":
        print("[argilla-bootstrap] dataset already published — schema is frozen.")
        print("                    To change schema: drop & recreate the dataset.")
        return 0

    for f in FIELDS:
        ag.add_field(ds["id"], f)
    for q in QUESTIONS:
        ag.add_question(ds["id"], q)
    for m in METADATA_PROPERTIES:
        ag.add_metadata(ds["id"], m)
    for v in _vector_settings(vector_dim):
        ag.add_vector(ds["id"], v)
    ag.publish(ds["id"])
    print(f"[argilla-bootstrap] dataset published with "
          f"{len(FIELDS)} fields / {len(QUESTIONS)} questions / "
          f"{len(METADATA_PROPERTIES)} metadata / 1 vector(dim={vector_dim})")
    return 0


def _argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Bootstrap text2sql Argilla schema.")
    p.add_argument("--url", default="http://localhost:6900")
    p.add_argument("--api-key", default="owner.apikey")
    p.add_argument("--workspace", default="admin")
    p.add_argument("--dataset", default="text2sql-feedback")
    p.add_argument("--vector-dim", type=int, default=384,
                   help="Must equal the embedding dim used by the question embedder (TEI/bge).")
    return p


if __name__ == "__main__":
    args = _argparser().parse_args()
    sys.exit(
        bootstrap(
            url=args.url,
            api_key=args.api_key,
            workspace=args.workspace,
            dataset=args.dataset,
            vector_dim=args.vector_dim,
        )
    )
