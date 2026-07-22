"""HuggingFace Text-Embeddings-Inference (TEI) HTTP client.

POST /embed  body: {"inputs": [str, ...]}  -> [[float, ...], ...]

We use raw HTTP rather than the SDK because the TEI surface is tiny.
"""

from __future__ import annotations

import httpx

from app.observability import get_logger
from app.settings import get_settings

_log = get_logger(__name__)


async def embed(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    s = get_settings()
    async with httpx.AsyncClient(timeout=15.0) as cx:
        r = await cx.post(f"{s.tei_url}/embed", json={"inputs": texts})
        r.raise_for_status()
        return r.json()
