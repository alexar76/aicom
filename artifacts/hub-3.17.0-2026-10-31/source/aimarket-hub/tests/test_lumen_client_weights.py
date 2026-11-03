"""LUMEN (PageRank) takes only non-negative weights; the hub's graph also holds penalties.

On 2026-09-26 one invoke_failure edge (-0.25) made every score request fail with
"trust weight must be non-negative", read as an unavailable oracle: from then on every new
publisher on modelmarket.dev was scored untrusted, hidden from search and refused at invoke.
"""
import httpx

from aimarket_hub import lumen_client
from aimarket_hub.lumen_client import LumenTrustClient


def _capture(monkeypatch):
    sent = {}
    real = httpx.Client

    def handler(request):
        sent["body"] = __import__("json").loads(request.content)
        n = sent["body"]["input"]["nodes"]
        return httpx.Response(200, json={"output": {"scores": [1.0 / n] * n}})

    monkeypatch.setattr(lumen_client.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(handler)))
    return sent


def test_penalties_are_netted_never_sent_negative(monkeypatch):
    sent = _capture(monkeypatch)
    edges = [("consumer:anonymous", "ww", -0.25), ("consumer:anonymous", "ww", -0.25)] + \
            [("consumer:anonymous", "ww", 0.15)] * 6 + [("consumer:x", "bad", -0.25)]
    out = LumenTrustClient("https://lumen.example").score_entity("new-publisher", edges)
    weights = [e[2] for e in sent["body"]["input"]["edges"]]
    assert all(w > 0 for w in weights)
    assert weights == [0.15 * 6 - 0.5] or abs(weights[0] - 0.4) < 1e-9
    assert out["degraded"] is False


def test_a_graph_of_only_penalties_is_no_signal(monkeypatch):
    _capture(monkeypatch)
    out = LumenTrustClient("https://lumen.example").score_entity("p", [("c", "p", -0.25)])
    assert out["degraded"] is True and out["reason"] == "empty_graph"
