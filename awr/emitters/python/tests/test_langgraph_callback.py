"""The LangChain/LangGraph adapter, driven by a fake that implements the documented shape.

langchain-core is not installed here. These fakes reproduce the callback surface of
langchain-core 0.3.x — `on_llm_start(serialized, prompts, run_id=…)`,
`on_llm_end(LLMResult, run_id=…)`, `on_llm_error(exc, run_id=…)` — and nothing more. That
makes this a test of the adapter's logic, NOT evidence that it fits the real package; the
adapter's docstring says so too.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import pytest

from awr import SigningKey, verify_document
from awr_emitter.adapters.langgraph_callback import AwrReceiptCallback

SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")


@dataclass
class FakeGeneration:
    text: str


@dataclass
class FakeLLMResult:
    generations: List[List[FakeGeneration]] = field(default_factory=list)


@pytest.fixture()
def key() -> SigningKey:
    return SigningKey.from_seed(SEED)


def test_a_successful_call_produces_one_verifiable_receipt(key):
    cb = AwrReceiptCallback(key)
    cb.on_llm_start({"name": "ChatAnthropic"}, ["say hola"], run_id="r1",
                    invocation_params={"model": "claude-opus-5"})
    cb.on_llm_end(FakeLLMResult([[FakeGeneration("hola")]]), run_id="r1")

    assert len(cb.receipts) == 1
    result = verify_document(cb.receipts[0])
    assert result["valid"] is True, result["reasons"]
    subject = cb.receipts[0]["credentialSubject"]
    assert subject["work"]["modelId"] == "claude-opus-5"
    assert subject["work"]["status"] == "succeeded"
    assert isinstance(subject["work"]["latencyMs"], int)


def test_a_failed_call_still_produces_a_receipt(key):
    cb = AwrReceiptCallback(key)
    cb.on_llm_start({}, ["say hola"], run_id="r2")
    cb.on_llm_error(RuntimeError("upstream 500"), run_id="r2")

    assert len(cb.receipts) == 1
    doc = cb.receipts[0]
    assert verify_document(doc)["valid"] is True
    assert doc["credentialSubject"]["work"]["status"] == "failed"


def test_the_error_text_is_not_passed_off_as_model_output(key):
    """A receipt must not commit to bytes the model never produced."""
    cb = AwrReceiptCallback(key)
    cb.on_llm_start({}, ["p"], run_id="r3")
    cb.on_llm_error(RuntimeError("secret internal detail"), run_id="r3")

    empty = AwrReceiptCallback(key)
    empty.on_llm_start({}, ["p"], run_id="r4")
    empty.on_llm_end(FakeLLMResult([]), run_id="r4")

    assert (cb.receipts[0]["credentialSubject"]["outputDigest"]
            == empty.receipts[0]["credentialSubject"]["outputDigest"])


def test_the_same_prompts_digest_the_same_regardless_of_call(key):
    cb = AwrReceiptCallback(key)
    for run in ("a", "b"):
        cb.on_llm_start({}, ["one", "two"], run_id=run)
        cb.on_llm_end(FakeLLMResult([[FakeGeneration("x")]]), run_id=run)
    first, second = cb.receipts
    assert first["credentialSubject"]["inputDigest"] == second["credentialSubject"]["inputDigest"]
    # …and the documents still differ, because each has its own id and timestamp.
    assert first["id"] != second["id"]


def test_an_unknown_run_id_is_ignored_rather_than_guessed(key):
    """An end without a start is not a receipt: we do not know what was sent."""
    cb = AwrReceiptCallback(key)
    cb.on_llm_end(FakeLLMResult([[FakeGeneration("hola")]]), run_id="never-started")
    assert cb.receipts == []


def test_a_custom_sink_receives_the_documents(key):
    collected = []
    cb = AwrReceiptCallback(key, on_receipt=collected.append)
    cb.on_llm_start({}, ["p"], run_id="r")
    cb.on_llm_end(FakeLLMResult([[FakeGeneration("o")]]), run_id="r")
    assert len(collected) == 1 and cb.receipts == []


def test_the_model_falls_back_without_inventing_one(key):
    cb = AwrReceiptCallback(key, model_id="fallback@local")
    cb.on_llm_start({}, ["p"], run_id="r")
    cb.on_llm_end(FakeLLMResult([[FakeGeneration("o")]]), run_id="r")
    assert cb.receipts[0]["credentialSubject"]["work"]["modelId"] == "fallback@local"
