"""Emit an AWR/2 receipt for every LLM call in a LangChain / LangGraph run.

WHAT THIS WAS WRITTEN AGAINST, AND WHAT IT WAS TESTED AGAINST — read this before trusting
it in production. The callback surface here is `langchain_core.callbacks.BaseCallbackHandler`
as documented for langchain-core 0.3.x: `on_llm_start(serialized, prompts, **kwargs)`,
`on_llm_end(response, **kwargs)` and `on_llm_error(error, **kwargs)`, with `run_id` arriving
as a keyword argument. langchain-core is **not installed here and was not imported**; this
adapter is duck-typed against that shape and its test drives it with a local fake that
implements the same calls. If the real package has moved, this file is where it breaks, and
the test will not tell you — run it once against your actual version.

It deliberately does not subclass anything: importing langchain-core to inherit from it
would make an emitter that is supposed to cost nothing drag in a dependency tree.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional

from awr import SigningKey

from awr_emitter import emit_receipt, jcs_payload

__all__ = ["AwrReceiptCallback"]


class AwrReceiptCallback:
    """Collects one signed ``WorkReceipt`` per LLM call.

    Args:
        key: the signing key; its ``did`` is the issuer of every receipt.
        model_id: what to record as ``work.modelId`` when the framework does not say.
        on_receipt: called with each signed document. Defaults to appending to
            :attr:`receipts`, which is fine for a script and wrong for a long-running
            process — pass a sink that writes them somewhere.

    A failed call still produces a receipt, with ``status`` ``failed`` and the digest of
    the empty payload as its output: §3.3 keeps a failure first-class because that is the
    case a dispute most often turns on.
    """

    def __init__(
        self,
        key: SigningKey,
        *,
        model_id: str = "unknown@unknown",
        on_receipt: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        self.key = key
        self.model_id = model_id
        self.receipts: List[Dict[str, Any]] = []
        self._on_receipt = on_receipt or self.receipts.append
        self._runs: Dict[Any, Dict[str, Any]] = {}

    # ── the three callbacks ────────────────────────────────────────────────

    def on_llm_start(self, serialized: Any, prompts: List[str], **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        self._runs[run_id] = {
            "started": time.monotonic(),
            # The prompt list is the input, canonicalized so a third party holding the same
            # prompts computes the same digest regardless of how their JSON orders things.
            "input": jcs_payload(list(prompts)),
            "model": self._model_from(serialized, kwargs),
        }

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        state = self._runs.pop(kwargs.get("run_id"), None)
        if state is None:
            return
        self._emit(state, self._texts_of(response), "succeeded")

    def on_llm_error(self, error: BaseException, **kwargs: Any) -> None:
        state = self._runs.pop(kwargs.get("run_id"), None)
        if state is None:
            return
        # The error text is NOT digested as output: it is our narration of the failure, not
        # the model's output, and putting it in outputDigest would misrepresent what the
        # receipt commits to.
        self._emit(state, b"", "failed")

    # ── internals ──────────────────────────────────────────────────────────

    def _emit(self, state: Dict[str, Any], output: Any, status: str) -> None:
        latency = int((time.monotonic() - state["started"]) * 1000)
        document = emit_receipt(
            key=self.key,
            model_id=state["model"],
            input_payload=state["input"],
            output_payload=output,
            status=status,
            latency_ms=latency,
        )
        self._on_receipt(document)

    def _model_from(self, serialized: Any, kwargs: Dict[str, Any]) -> str:
        params = kwargs.get("invocation_params") or {}
        for source in (params, serialized if isinstance(serialized, dict) else {}):
            for field in ("model", "model_name", "model_id"):
                value = source.get(field)
                if isinstance(value, str) and value:
                    return value
        if isinstance(serialized, dict):
            name = serialized.get("name") or (serialized.get("id") or [None])[-1]
            if isinstance(name, str) and name:
                return name
        return self.model_id

    @staticmethod
    def _texts_of(response: Any) -> bytes:
        """The generated text, canonicalized as a list of strings.

        `LLMResult.generations` is a list of lists of Generation objects. Anything we
        cannot read is recorded as the empty payload rather than guessed at — an emitter
        that invents an output digest is worse than one that admits it has none.
        """
        generations = getattr(response, "generations", None)
        if not generations:
            return b""
        texts: List[str] = []
        for batch in generations:
            for generation in batch or ():
                text = getattr(generation, "text", None)
                if isinstance(text, str):
                    texts.append(text)
        return jcs_payload(texts) if texts else b""
