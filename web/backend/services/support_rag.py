"""
Lightweight lexical RAG for the public support agent.

Loads:
1) Bundled baseline markdown (platform facts).
2) Optional owner knowledge: `AIFACTORY_SUPPORT_KB_DIR` — `*.md` and `*.txt` (UTF-8).

Retrieval: token overlap scoring over fixed-size chunks (no embeddings dependency — production-simple).
Also indexes **all pipeline products** (marketplace / catalog) so support can answer product questions.

Disable with AIFACTORY_SUPPORT_RAG_ENABLED=0.
Marketplace index disable: AIFACTORY_SUPPORT_RAG_MARKETPLACE=0
"""

from __future__ import annotations

import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

from web.backend.services.prompt_safety import prepare_untrusted_plain_text

logger = logging.getLogger(__name__)

_BASELINE = Path(__file__).resolve().parent / "support_rag_baseline.md"
_CHUNK = 900
_OVERLAP = 120
_TOP_K = 10
_MAX_INJECT = 9000
_CACHE_TTL_SEC = 60.0
_MARKETPLACE_CACHE_TTL = 120.0

_doc_cache: tuple[float, list[tuple[str, str]]] | None = None
_market_chunks_cache: tuple[float, list[tuple[str, str]]] | None = None


def _truthy(name: str, default: str = "1") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes")


def _kb_dir() -> Path:
    return Path(os.environ.get("AIFACTORY_SUPPORT_KB_DIR", "/app/data/support/knowledge"))


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in re.findall(r"[\w\-]{2,}", text, flags=re.UNICODE) if len(t) >= 2}


def _chunk_text(source: str, body: str) -> list[tuple[str, str]]:
    body = body.strip()
    if not body:
        return []
    chunks: list[tuple[str, str]] = []
    i = 0
    while i < len(body):
        piece = body[i : i + _CHUNK]
        if len(body) > i + _CHUNK:
            cut = piece.rfind("\n\n")
            if cut > _CHUNK // 3:
                piece = piece[:cut]
        piece = piece.strip()
        step = max(len(piece) - _OVERLAP, _CHUNK // 2) if piece else _CHUNK
        if piece:
            chunks.append((source, piece))
        i += step
        if step <= 0:
            i = len(body)
    return chunks


def _load_all_documents() -> list[tuple[str, str]]:
    """Return list of (source_label, full_text)."""
    out: list[tuple[str, str]] = []

    if _BASELINE.is_file():
        try:
            out.append(("baseline", _BASELINE.read_text(encoding="utf-8", errors="replace")))
        except OSError as e:
            logger.warning("support_rag: cannot read baseline: %s", e)

    kb = _kb_dir()
    if kb.is_dir():
        for pattern in ("*.md", "*.txt"):
            for p in sorted(kb.glob(pattern)):
                if not p.is_file():
                    continue
                try:
                    txt = p.read_text(encoding="utf-8", errors="replace")
                    out.append((p.name, txt))
                except OSError as e:
                    logger.warning("support_rag: skip %s: %s", p, e)
    return out


def _cached_docs() -> list[tuple[str, str]]:
    global _doc_cache
    now = time.time()
    if _doc_cache and now - _doc_cache[0] < _CACHE_TTL_SEC:
        return _doc_cache[1]
    docs = _load_all_documents()
    _doc_cache = (now, docs)
    return docs


def _marketplace_enabled() -> bool:
    return _truthy("AIFACTORY_SUPPORT_RAG_MARKETPLACE", "1")


def _load_marketplace_chunks() -> list[tuple[str, str]]:
    """(label, chunk) for every pipeline product — sanitized; same host as products API."""
    global _market_chunks_cache
    now = time.time()
    if _market_chunks_cache and now - _market_chunks_cache[0] < _MARKETPLACE_CACHE_TTL:
        return _market_chunks_cache[1]
    chunks: list[tuple[str, str]] = []
    try:
        from web.backend.api import products as products_api

        pmap = products_api._get_products_map()
    except Exception as e:
        logger.warning("support_rag: marketplace load failed: %s", e)
        _market_chunks_cache = (now, [])
        return []

    compact_lines: list[str] = []
    for pid in sorted(pmap.keys())[:900]:
        p = pmap[pid]
        st = (p.get("state") or "").upper()
        try:
            mkt = products_api._load_marketing(pid)
            name = prepare_untrusted_plain_text(str(products_api._get_product_name(pid)), max_len=200)
            if mkt.get("product_name"):
                name = prepare_untrusted_plain_text(str(mkt.get("product_name")), max_len=200)
            idea = prepare_untrusted_plain_text(str(p.get("idea") or ""), max_len=600)
            desc = prepare_untrusted_plain_text(
                str(mkt.get("selling_description") or mkt.get("short_description") or ""),
                max_len=1500,
            )
            cat = products_api._canonical_marketplace_category(mkt, p)
            tags = mkt.get("tags") or p.get("tags") or []
            tags_s = prepare_untrusted_plain_text(
                ", ".join(str(t) for t in tags[:12] if t),
                max_len=400,
            )
        except Exception:
            name = pid
            idea = ""
            desc = ""
            cat = "uncategorized"
            tags_s = ""

        compact_lines.append(f"{pid} | {st} | {name} | {cat}")
        body = (
            f"product_id: {pid}\nstate: {st}\ncategory: {cat}\nname: {name}\n"
            f"tags: {tags_s}\nidea: {idea}\ndescription: {desc}\n"
        )
        for _src, piece in _chunk_text(f"mp-{pid}", body):
            chunks.append((f"product:{pid}", piece))

    header = (
        "# Marketplace — registered products (compact index; same rows as pipeline)\n"
        + "\n".join(compact_lines)
    )
    header = prepare_untrusted_plain_text(header, max_len=18000)
    out: list[tuple[str, str]] = [("marketplace-index", header)] + chunks
    _market_chunks_cache = (now, out)
    return out


def retrieve_support_context(*, user_message: str, history_snippets: Optional[list[dict[str, str]]] = None) -> str:
    """
    Return a single markdown-ish block to inject into the LLM system prompt (not shown raw to users).
    """
    if not _truthy("AIFACTORY_SUPPORT_RAG_ENABLED", "1"):
        return ""

    query_parts = [user_message or ""]
    if history_snippets:
        for m in history_snippets[-6:]:
            if (m.get("role") or "").lower() == "user":
                query_parts.append(str(m.get("content") or "")[:500])
    query = " ".join(query_parts)
    q_tokens = _tokenize(query)
    if not q_tokens:
        q_tokens = _tokenize("ai factory marketplace sandbox pipeline support")

    all_chunks: list[tuple[str, str, int]] = []

    if _marketplace_enabled():
        for label, chunk in _load_marketplace_chunks():
            ct = _tokenize(chunk)
            score = len(q_tokens & ct)
            if label == "marketplace-index":
                score = max(score, 2)
            chunk_l = chunk.lower()
            for tok in q_tokens:
                if tok.startswith("prod-") and tok in chunk_l:
                    score += 5
            if score > 0 or label == "marketplace-index":
                all_chunks.append((label, chunk, score))

    for source, text in _cached_docs():
        for label, chunk in _chunk_text(source, text):
            ct = _tokenize(chunk)
            score = len(q_tokens & ct)
            if "#" in chunk[:80]:
                score += 1
            if score > 0:
                all_chunks.append((label, chunk, score))

    all_chunks.sort(key=lambda x: -x[2])
    picked: list[str] = []
    total = 0
    per_source: dict[str, int] = {}

    # Always keep compact marketplace index first when marketplace RAG is on
    if _marketplace_enabled():
        for label, chunk, sc in all_chunks:
            if label == "marketplace-index":
                block = f"### [{label}] (score={sc})\n{chunk}\n"
                if total + len(block) <= _MAX_INJECT:
                    picked.append(block)
                    total += len(block)
                break

    for label, chunk, sc in all_chunks:
        if label == "marketplace-index":
            continue
        if per_source.get(label, 0) >= 2:
            continue
        block = f"### [{label}] (score={sc})\n{chunk}\n"
        if total + len(block) > _MAX_INJECT:
            break
        picked.append(block)
        total += len(block)
        per_source[label] = per_source.get(label, 0) + 1
        if len(picked) >= _TOP_K:
            break

    if not picked:
        for source, text in _cached_docs():
            for label, chunk in _chunk_text(source, text):
                return f"### [{label}]\n{chunk[:2500]}\n"
        if _marketplace_enabled():
            mc = _load_marketplace_chunks()
            if mc:
                return f"### [{mc[0][0]}]\n{mc[0][1][:2500]}\n"
        return ""

    return "\n".join(picked)
