"""An oracle's signed receipt must not hide a lost A2A delivery (live GAIA regression)."""
import pytest

from aimarket_hub.a2a import _Invoke, _completed


@pytest.mark.parametrize("body, expected", [
    ({"output": {"reading": {"values": {"temperature": 12}}}},
     {"reading": {"values": {"temperature": 12}}}),
    ({"output": "weather text"}, "weather text"),
    ({"output": [0, False]}, [0, False]),
    ({"output": False}, False),
    ({"result": {"answer": 42}, "output": {"answer": 0}}, {"answer": 42}),
    ({"result": None, "output": {"answer": 42}}, None),
])
def test_completed_preserves_oracle_output_and_result_precedence(body, expected):
    receipt = {"nonce": "provider-receipt", "signature": {"value": "unchanged"}}
    outcome = _completed(
        {**body, "receipt": receipt, "price_usd": 0.001},
        task_id="task", context_id="context",
        invoke=_Invoke(raw=b"{}", product_id="gaia.gateway",
                       capability_id="gaia.weather.read@v1", source_hub="https://provider.test"),
        hub_url="https://hub.test", payment=None,
    )
    part = outcome.artifacts[0]["parts"][0]
    assert part.get("data", part.get("text")) == expected
    assert outcome.artifacts[1]["parts"][0]["data"] == receipt
    assert outcome.artifacts[1]["metadata"]["signerWellKnown"] == "https://provider.test/.well-known/ai-market.json"
