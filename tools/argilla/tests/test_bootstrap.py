"""Unit tests for tools/argilla/bootstrap.py — pure HTTP contract test.

We mock httpx.Client so the test runs without a live Argilla instance.
"""

from __future__ import annotations

from typing import Any

import pytest

from tools.argilla import bootstrap as bs


class _Resp:
    def __init__(self, status_code: int = 200, body: Any | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}
        self.text = ""

    def json(self) -> Any:
        return self._body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _RecordingClient:
    """In-memory fake of httpx.Client that records every request."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        # By default: workspace missing, dataset missing, then created.
        self._ws_items: list[dict[str, Any]] = []
        self._ds_items: list[dict[str, Any]] = []

    # GET / POST / PUT --------------------------------------------------
    def get(self, path: str, params: dict | None = None) -> _Resp:
        self.calls.append(("GET", path, None))
        if path == "/api/_status":
            return _Resp(200, {"version": "fake"})
        if path == "/api/v1/me":
            return _Resp(200, {"username": "owner"})
        if path == "/api/v1/me/workspaces":
            return _Resp(200, {"items": self._ws_items})
        if path == "/api/v1/me/datasets":
            return _Resp(200, {"items": self._ds_items})
        return _Resp(404)

    def post(self, path: str, json: dict | None = None) -> _Resp:
        self.calls.append(("POST", path, json))
        if path == "/api/v1/workspaces":
            ws = {"id": "ws-1", "name": json["name"]}
            self._ws_items.append(ws)
            return _Resp(201, ws)
        if path == "/api/v1/datasets":
            ds = {"id": "ds-1", "name": json["name"], "workspace_id": json["workspace_id"], "status": "draft"}
            self._ds_items.append(ds)
            return _Resp(201, ds)
        if path.endswith("/fields") or path.endswith("/questions") \
           or path.endswith("/metadata-properties") or path.endswith("/vectors-settings"):
            return _Resp(201, {})
        return _Resp(201, {})

    def put(self, path: str, json: dict | None = None) -> _Resp:
        self.calls.append(("PUT", path, json))
        return _Resp(200, {})

    # not used --------------------------------------------------------
    def patch(self, *a, **kw): raise NotImplementedError


@pytest.fixture
def fake_argilla(monkeypatch: pytest.MonkeyPatch) -> _RecordingClient:
    fake = _RecordingClient()

    def _factory(*args, **kwargs):
        return fake

    monkeypatch.setattr(bs.httpx, "Client", _factory)
    return fake


def test_bootstrap_creates_full_schema_when_missing(fake_argilla: _RecordingClient) -> None:
    rc = bs.bootstrap(
        url="http://argilla:6900",
        api_key="owner.apikey",
        workspace="admin",
        dataset="text2sql-feedback",
        vector_dim=384,
    )
    assert rc == 0
    paths = [c[1] for c in fake_argilla.calls]
    assert "/api/v1/me/workspaces" in paths       # GET (lookup, v1.29+v2 compatible)
    assert "/api/v1/workspaces" in paths          # POST to create when missing
    assert any(p == "/api/v1/datasets" for p in paths)
    field_calls = [c for c in fake_argilla.calls if c[1].endswith("/fields") and c[0] == "POST"]
    question_calls = [c for c in fake_argilla.calls if c[1].endswith("/questions") and c[0] == "POST"]
    md_calls = [c for c in fake_argilla.calls if c[1].endswith("/metadata-properties") and c[0] == "POST"]
    vec_calls = [c for c in fake_argilla.calls if c[1].endswith("/vectors-settings") and c[0] == "POST"]
    assert len(field_calls) == len(bs.FIELDS) == 6
    assert len(question_calls) == len(bs.QUESTIONS) == 3
    assert len(md_calls) == len(bs.METADATA_PROPERTIES) == 14
    assert len(vec_calls) == 1
    publish_calls = [c for c in fake_argilla.calls if c[0] == "PUT" and c[1].endswith("/publish")]
    assert len(publish_calls) == 1


def test_bootstrap_idempotent_when_already_published(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _RecordingClient()
    fake._ws_items.append({"id": "ws-1", "name": "admin"})
    fake._ds_items.append({"id": "ds-1", "name": "text2sql-feedback", "workspace_id": "ws-1", "status": "ready"})
    monkeypatch.setattr(bs.httpx, "Client", lambda *a, **kw: fake)
    rc = bs.bootstrap(
        url="http://argilla:6900",
        api_key="owner.apikey",
        workspace="admin",
        dataset="text2sql-feedback",
        vector_dim=384,
    )
    assert rc == 0
    # No field/question/metadata creation — schema is frozen.
    posts = [c for c in fake.calls if c[0] == "POST"]
    assert posts == []
    puts = [c for c in fake.calls if c[0] == "PUT"]
    assert puts == []
