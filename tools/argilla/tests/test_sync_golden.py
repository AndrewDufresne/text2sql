"""Unit tests for tools/argilla/sync_golden.py."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from tools.argilla import sync_golden as sg


class _Resp:
    def __init__(self, status_code: int = 200, body: Any | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _Cli:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.patches: list[tuple[str, dict[str, Any]]] = []

    def get(self, path: str, params: dict | None = None) -> _Resp:
        if path == "/api/v1/workspaces":
            return _Resp(200, {"items": [{"id": "ws-1", "name": "admin"}]})
        if path == "/api/v1/me/datasets":
            return _Resp(200, {"items": [{"id": "ds-1", "name": "text2sql-feedback", "workspace_id": "ws-1"}]})
        if path.endswith("/records"):
            return _Resp(200, {"items": self.records})
        return _Resp(404)

    def patch(self, path: str, json: dict | None = None) -> _Resp:
        self.patches.append((path, json or {}))
        return _Resp(200, {})


@pytest.fixture
def golden_path(tmp_path: Path) -> Path:
    p = tmp_path / "golden_set.yaml"
    p.write_text(
        yaml.safe_dump(
            {"threshold_pass_rate": 0.9, "cases": [{"id": "existing", "role": "RM", "question": "x", "expect": {"status": "ok"}}]}
        ),
        encoding="utf-8",
    )
    return p


def _good_record(rid: str = "rec-1") -> dict[str, Any]:
    return {
        "id": rid,
        "fields": {
            "question": "How many active clients?",
            "corrected_sql": "SELECT count(*) FROM client WHERE is_active LIMIT 1",
        },
        "metadata": {
            "trace_id": "trace-x",
            "user_role": "RM",
            "tables_used": ["client"],
            "tags": ["hitl"],
            "reviewed": True,
        },
    }


def _bad_record() -> dict[str, Any]:
    return {
        "id": "rec-bad",
        "fields": {"question": "broken", "corrected_sql": "SELEKT *** FROMM ((("},
        "metadata": {"reviewed": True},
    }


def _already_synced() -> dict[str, Any]:
    r = _good_record("rec-2")
    r["metadata"]["golden_set_id"] = "hitl-foo-1"
    return r


def _not_reviewed() -> dict[str, Any]:
    r = _good_record("rec-3")
    r["metadata"]["reviewed"] = False
    return r


def test_sync_appends_promotable_only(monkeypatch: pytest.MonkeyPatch, golden_path: Path) -> None:
    cli = _Cli([_good_record(), _already_synced(), _not_reviewed()])
    monkeypatch.setattr(sg.httpx, "Client", lambda *a, **kw: cli)

    rc = sg.sync(
        url="http://argilla:6900",
        api_key="owner.apikey",
        workspace="admin",
        dataset="text2sql-feedback",
        golden_path=golden_path,
        dry_run=False,
    )
    assert rc == 0  # no rejected
    doc = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    case_ids = [c["id"] for c in doc["cases"]]
    assert "existing" in case_ids
    new_cases = [c for c in doc["cases"] if c["id"].startswith("hitl-")]
    assert len(new_cases) == 1
    assert new_cases[0]["question"].startswith("How many active")
    assert new_cases[0]["expect"]["tables_used"] == ["client"]
    # PATCH must mark the record as promoted to avoid double-import.
    assert any(
        (p[1].get("metadata") or {}).get("golden_set_id") for p in cli.patches
    )


def test_sync_rejects_bad_sql_and_unmarks_reviewed(monkeypatch: pytest.MonkeyPatch, golden_path: Path) -> None:
    cli = _Cli([_bad_record()])
    monkeypatch.setattr(sg.httpx, "Client", lambda *a, **kw: cli)
    # Force the validator path to run with a stub that rejects everything to
    # avoid coupling on whether the test env can import app.nodes.sql_validate.
    monkeypatch.setattr(sg, "_sql_validate", lambda sql: type("R", (), {"safe": False, "violations": ["parse_error: x"]})())

    rc = sg.sync(
        url="http://argilla:6900",
        api_key="owner.apikey",
        workspace="admin",
        dataset="text2sql-feedback",
        golden_path=golden_path,
        dry_run=False,
    )
    assert rc == 2  # any rejection -> exit 2
    # Golden set unchanged save for the existing case.
    doc = yaml.safe_load(golden_path.read_text(encoding="utf-8"))
    assert [c["id"] for c in doc["cases"]] == ["existing"]
    # Argilla record marked reviewed=False so SME revisits it.
    assert any(
        (p[1].get("metadata") or {}).get("reviewed") is False for p in cli.patches
    )


def test_sync_dry_run_writes_nothing(monkeypatch: pytest.MonkeyPatch, golden_path: Path) -> None:
    cli = _Cli([_good_record()])
    monkeypatch.setattr(sg.httpx, "Client", lambda *a, **kw: cli)
    before = golden_path.read_text(encoding="utf-8")

    rc = sg.sync(
        url="http://argilla:6900",
        api_key="owner.apikey",
        workspace="admin",
        dataset="text2sql-feedback",
        golden_path=golden_path,
        dry_run=True,
    )
    assert rc == 0
    assert golden_path.read_text(encoding="utf-8") == before
    # No PATCH in dry-run.
    assert cli.patches == []
