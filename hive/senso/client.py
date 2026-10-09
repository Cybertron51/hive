"""Verified knowledge base: Senso v2 client plus a local JSON fallback with the same interface.

    kb = get_kb()
    node_id = await kb.ingest_claim(claim)
    await kb.wait_processed(node_id)
    passages = await kb.context("What did Acme report about its phase 2 trial?")
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from hive.config import settings
from hive.models import Claim, new_id

SOURCE_RE = re.compile(r"^Source:\s*(\S+)", re.MULTILINE)
LOCAL_KB_PATH = Path("data/kb.json")


class SensoError(RuntimeError):
    pass


class SensoCreditsExhausted(SensoError):
    """402 from Senso: the org is out of credits. Callers should fall back or stop, not retry."""


class Passage(BaseModel):
    text: str
    title: str = ""
    source_url: str = ""
    node_id: str = ""
    content_id: str = ""
    score: float = 0.0


def claim_title(claim: Claim) -> str:
    return f"{claim.entity} | {claim.claim_type} | {claim.claim_id[:8]}"


def claim_text(claim: Claim) -> str:
    lines = [
        claim.text.strip(),
        "",
        f"Entity: {claim.entity}",
        f"Claim type: {claim.claim_type}",
    ]
    if claim.value:
        lines.append(f"Value: {claim.value}")
    lines += [
        f"Source: {claim.source_id}",
        f"Confidence: {claim.confidence:.2f}",
        f"Claim ID: {claim.claim_id}",
    ]
    return "\n".join(lines)


def _source_url(text: str) -> str:
    m = SOURCE_RE.search(text)
    return m.group(1) if m else ""


class KnowledgeBase(Protocol):
    async def me(self) -> dict[str, Any]: ...
    async def ingest_claim(self, claim: Claim, source_url: str = "") -> str: ...
    async def wait_processed(self, node_id: str, timeout: float = 60) -> bool: ...
    async def search(self, query: str) -> dict[str, Any]: ...
    async def context(self, query: str) -> list[Passage]: ...


class SensoKB:
    def __init__(self, api_key: str, base_url: str = settings.senso_base_url, timeout: float = 30):
        if not api_key:
            raise SensoError("SENSO_API_KEY is empty")
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers={"X-API-Key": api_key, "Content-Type": "application/json"},
            timeout=timeout,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> httpx.Response:
        try:
            resp = await self._http.request(method, path, json=json_body)
        except httpx.HTTPError as e:
            raise SensoError(f"{method} {path} failed: {type(e).__name__}") from e
        if resp.status_code == 402:
            raise SensoCreditsExhausted(f"{method} {path}: Senso credits exhausted (402)")
        if resp.status_code == 401:
            raise SensoError(f"{method} {path}: invalid or missing Senso API key (401)")
        return resp

    @staticmethod
    def _json(resp: httpx.Response, what: str) -> dict[str, Any]:
        if resp.status_code >= 400:
            raise SensoError(f"{what}: HTTP {resp.status_code}: {resp.text[:300]}")
        try:
            data = resp.json()
        except ValueError as e:
            raise SensoError(f"{what}: non-JSON response") from e
        if not isinstance(data, dict):
            raise SensoError(f"{what}: unexpected response shape")
        return data

    async def me(self) -> dict[str, Any]:
        return self._json(await self._request("GET", "/org/me"), "me")

    async def ingest_claim(self, claim: Claim, source_url: str = "") -> str:
        """Returns the kb_node_id, or "" if Senso already holds identical text (409)."""
        if source_url:
            claim = claim.model_copy(update={"source_id": source_url})
        resp = await self._request("POST", "/org/kb/raw", {"title": claim_title(claim), "text": claim_text(claim)})
        if resp.status_code == 409:
            return ""
        data = self._json(resp, "ingest_claim")
        node_id = data.get("kb_node_id") or ""
        if not node_id:
            raise SensoError("ingest_claim: response missing kb_node_id")
        return node_id

    async def node_status(self, node_id: str) -> str:
        data = self._json(await self._request("GET", f"/org/kb/nodes/{node_id}"), "node_status")
        content = data.get("content") or {}
        return content.get("processing_status") or data.get("processing_status") or "unknown"

    async def wait_processed(self, node_id: str, timeout: float = 60, interval: float = 3) -> bool:
        if not node_id:
            return True
        deadline = time.monotonic() + timeout
        while True:
            status = await self.node_status(node_id)
            if status == "complete":
                return True
            if status == "failed":
                raise SensoError(f"Senso failed to process node {node_id}")
            if time.monotonic() >= deadline:
                return False
            await asyncio.sleep(interval)

    async def search(self, query: str) -> dict[str, Any]:
        return self._json(await self._request("POST", "/org/search", {"query": query}), "search")

    async def context(self, query: str) -> list[Passage]:
        data = self._json(await self._request("POST", "/org/search/context", {"query": query}), "context")
        passages = []
        for r in data.get("results") or []:
            text = r.get("chunk_text") or ""
            if not text:
                continue
            passages.append(
                Passage(
                    text=text,
                    title=r.get("title") or "",
                    source_url=_source_url(text),
                    node_id=r.get("kb_node_id") or "",
                    content_id=r.get("content_id") or "",
                    score=float(r.get("score") or 0.0),
                )
            )
        return passages


class LocalKB:
    """Offline stand-in for Senso, backed by a JSON file. Ranking is plain token overlap."""

    def __init__(self, path: Path = LOCAL_KB_PATH, max_results: int = 8):
        self.path = path
        self.max_results = max_results
        self._lock = asyncio.Lock()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as e:
            raise SensoError(f"LocalKB: cannot read {self.path}: {e}") from e
        return data if isinstance(data, list) else []

    def _save(self, nodes: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(nodes, indent=2))
        os.replace(tmp, self.path)

    async def me(self) -> dict[str, Any]:
        return {"org_id": "local", "name": "LocalKB", "slug": "local", "is_free_tier": True, "path": str(self.path)}

    async def ingest_claim(self, claim: Claim, source_url: str = "") -> str:
        if source_url:
            claim = claim.model_copy(update={"source_id": source_url})
        text = claim_text(claim)
        async with self._lock:
            nodes = self._load()
            if any(n["text"] == text for n in nodes):
                return ""
            node_id = new_id()
            nodes.append({"kb_node_id": node_id, "title": claim_title(claim), "text": text})
            self._save(nodes)
        return node_id

    async def wait_processed(self, node_id: str, timeout: float = 60) -> bool:
        return True

    @staticmethod
    def _tokens(s: str) -> set[str]:
        return {t for t in re.findall(r"[a-z0-9]+", s.lower()) if len(t) > 2}

    async def context(self, query: str) -> list[Passage]:
        q = self._tokens(query)
        scored = []
        for n in self._load():
            overlap = len(q & self._tokens(n["title"] + " " + n["text"]))
            if overlap:
                scored.append((overlap / max(len(q), 1), n))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            Passage(text=n["text"], title=n["title"], source_url=_source_url(n["text"]), node_id=n["kb_node_id"], score=s)
            for s, n in scored[: self.max_results]
        ]

    async def search(self, query: str) -> dict[str, Any]:
        passages = await self.context(query)
        return {
            "query": query,
            "answer": "",
            "results": [{"title": p.title, "chunk_text": p.text, "score": p.score, "rank": i + 1} for i, p in enumerate(passages)],
            "total_results": len(passages),
        }


_kb: KnowledgeBase | None = None


def get_kb() -> KnowledgeBase:
    global _kb
    if _kb is None:
        _kb = SensoKB(settings.senso_api_key) if settings.senso_api_key else LocalKB()
    return _kb
