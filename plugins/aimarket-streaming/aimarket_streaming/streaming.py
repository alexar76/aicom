"""Streaming + Per-Chunk Billing (#11)

SSE/WS mode: capability streams tokens, every N tokens → micro-receipt.
Consumer can cancel mid-stream, paying only for what was received.

Implements token-level micropayment tracking with signed per-chunk receipts
and cumulative billing.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from aimarket_hub.signing import Signer


@dataclass
class ChunkReceipt:
    """A micro-receipt for a chunk of streamed output."""

    chunk_index: int
    token_count: int
    cumulative_tokens: int
    price_per_token_usd: float
    chunk_price_usd: float
    cumulative_price_usd: float
    timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    signature: str = ""

    def sign(self, signer: Signer) -> "ChunkReceipt":
        canonical = (
            f"chunk:{self.chunk_index}"
            f"|tokens:{self.token_count}"
            f"|cum_tokens:{self.cumulative_tokens}"
            f"|price:{self.chunk_price_usd}"
            f"|cum_price:{self.cumulative_price_usd}"
            f"|ts:{self.timestamp}"
        )
        self.signature = signer.sign_canonical(canonical)
        return self


@dataclass
class StreamSession:
    """An active streaming session."""

    session_id: str
    capability_id: str
    product_id: str
    channel_id: str
    price_per_token_usd: float
    tokens_per_chunk: int = 10
    total_tokens: int = 0
    total_price_usd: float = 0.0
    chunks: list[ChunkReceipt] = field(default_factory=list)
    cancelled: bool = False
    started_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))


class StreamingBiller:
    """Token-level micropayment tracker for streaming invocations.

    Usage:
        biller = StreamingBiller(signer)
        session = biller.open_session("cap@v1", "prod-1", "ch_123", 0.001)

        async for chunk in biller.stream_tokens(session, token_generator):
            # chunk = {"tokens": [...], "chunk_receipt": {...}, "cumulative_price": 0.05}
            yield chunk
    """

    def __init__(self, signer: Signer | None = None):
        self.signer = signer or Signer()
        self._sessions: dict[str, StreamSession] = {}

    def open_session(
        self,
        capability_id: str,
        product_id: str,
        channel_id: str,
        price_per_token_usd: float = 0.001,
        tokens_per_chunk: int = 10,
    ) -> StreamSession:
        session_id = f"stream_{int(time.time())}_{capability_id[:8]}"
        session = StreamSession(
            session_id=session_id,
            capability_id=capability_id,
            product_id=product_id,
            channel_id=channel_id,
            price_per_token_usd=price_per_token_usd,
            tokens_per_chunk=tokens_per_chunk,
        )
        self._sessions[session_id] = session
        return session

    async def stream_tokens(
        self,
        session: StreamSession,
        token_generator,
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream tokens with per-chunk billing.

        Args:
            session: Active streaming session
            token_generator: Async generator yielding individual token strings

        Yields:
            dict with tokens, chunk_receipt, cumulative_price
        """
        chunk_tokens: list[str] = []
        chunk_index = 0

        try:
            async for token in token_generator:
                if session.cancelled:
                    break

                chunk_tokens.append(token)
                session.total_tokens += 1

                if len(chunk_tokens) >= session.tokens_per_chunk:
                    chunk_index += 1
                    chunk_price = len(chunk_tokens) * session.price_per_token_usd
                    session.total_price_usd += chunk_price

                    receipt = ChunkReceipt(
                        chunk_index=chunk_index,
                        token_count=len(chunk_tokens),
                        cumulative_tokens=session.total_tokens,
                        price_per_token_usd=session.price_per_token_usd,
                        chunk_price_usd=round(chunk_price, 6),
                        cumulative_price_usd=round(session.total_price_usd, 6),
                    ).sign(self.signer)

                    session.chunks.append(receipt)

                    yield {
                        "tokens": list(chunk_tokens),
                        "chunk_receipt": {
                            "chunk_index": receipt.chunk_index,
                            "token_count": receipt.token_count,
                            "chunk_price_usd": receipt.chunk_price_usd,
                            "cumulative_price_usd": receipt.cumulative_price_usd,
                            "signature": receipt.signature,
                        },
                        "cumulative_tokens": session.total_tokens,
                        "cumulative_price_usd": session.cumulative_price_usd,
                        "session_id": session.session_id,
                    }
                    chunk_tokens = []

            # Final partial chunk
            if chunk_tokens and not session.cancelled:
                chunk_index += 1
                chunk_price = len(chunk_tokens) * session.price_per_token_usd
                session.total_price_usd += chunk_price

                receipt = ChunkReceipt(
                    chunk_index=chunk_index,
                    token_count=len(chunk_tokens),
                    cumulative_tokens=session.total_tokens,
                    price_per_token_usd=session.price_per_token_usd,
                    chunk_price_usd=round(chunk_price, 6),
                    cumulative_price_usd=round(session.total_price_usd, 6),
                ).sign(self.signer)

                session.chunks.append(receipt)

                yield {
                    "tokens": list(chunk_tokens),
                    "chunk_receipt": {
                        "chunk_index": receipt.chunk_index,
                        "token_count": receipt.token_count,
                        "chunk_price_usd": receipt.chunk_price_usd,
                        "cumulative_price_usd": receipt.cumulative_price_usd,
                        "signature": receipt.signature,
                    },
                    "cumulative_tokens": session.total_tokens,
                    "cumulative_price_usd": session.cumulative_price_usd,
                    "session_id": session.session_id,
                    "final": True,
                }

        except Exception:
            # On error, consumer only pays for received chunks
            pass

    def cancel_session(self, session_id: str) -> dict[str, Any]:
        """Cancel mid-stream — consumer pays only for received tokens."""
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "session not found"}

        session.cancelled = True
        return {
            "session_id": session_id,
            "cancelled": True,
            "total_tokens_received": session.total_tokens,
            "total_price_usd": round(session.total_price_usd, 6),
            "chunks_received": len(session.chunks),
            "refund_note": "Consumer pays only for received chunks. Remaining channel balance is intact.",
        }

    def get_session(self, session_id: str) -> StreamSession | None:
        return self._sessions.get(session_id)

    def session_summary(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "session not found"}

        return {
            "session_id": session.session_id,
            "capability_id": session.capability_id,
            "total_tokens": session.total_tokens,
            "total_price_usd": round(session.total_price_usd, 6),
            "chunks": len(session.chunks),
            "cancelled": session.cancelled,
            "duration_s": round(time.time() - time.mktime(time.strptime(session.started_at, "%Y-%m-%dT%H:%M:%SZ")), 1),
            "signed_receipts": [
                {"chunk": r.chunk_index, "price": r.chunk_price_usd, "sig": r.signature[:32] + "..."}
                for r in session.chunks[-5:]  # Last 5 receipts
            ],
        }
