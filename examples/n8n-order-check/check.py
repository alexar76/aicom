"""Real HTTP acceptance checks; requires the three workshop processes running."""
import json
import os
from pathlib import Path

import httpx
from aimarket_hub.signing import Signer
from aimarket_hub.supply_security import _bound_response_canonical

ROOT = Path(__file__).resolve().parent


def check():
    body = json.loads((ROOT / "request.json").read_text())
    with httpx.Client(timeout=20, trust_env=False) as client:
        assert client.post("http://127.0.0.1:13456/invoke", json=body).status_code == 401
        assert client.post("http://127.0.0.1:15678/webhook/aimarket-order-check", json=body["input"]).status_code in (401, 403)
        print("PASS: adapter and n8n reject unauthenticated calls")
        response = client.post("http://127.0.0.1:13456/invoke", json=body,
            headers={"X-AIMarket-Internal-Token": os.environ["AIMARKET_CAPABILITY_TOKEN"]})
        response.raise_for_status()
        result = response.json()["result"]
        pubkey = client.get("http://127.0.0.1:13456/healthz").json()["provider_pubkey"]
        signature = response.headers["X-Provider-Signature"]
        canonical = _bound_response_canonical(body["capability_id"], body["product_id"], body["input"], result)
        assert Signer.verify(pubkey, signature, canonical)
        assert not Signer.verify(pubkey, signature, canonical.replace('3430', '3431'))
        assert not Signer.verify(pubkey, signature,
            _bound_response_canonical(body["capability_id"], body["product_id"], {"items": []}, result))
        print("PASS: response signature verifies; result/input tampering fails")
        cases = [
            (body["input"], "ready", 3430),
            ({"items": [{"sku": "MUG-BLUE", "quantity": 4}]}, "insufficient_stock", 3400),
            ({"items": [{"sku": "NOT-FOUND", "quantity": 1}]}, "unknown_items", None),
            ({"items": [{"sku": "MUG-BLUE", "quantity": 2}, {"sku": "MUG-BLUE", "quantity": 2}]}, "insufficient_stock", 3400),
        ]
        for inp, status, subtotal in cases:
            response = client.post("http://127.0.0.1:19083/ai-market/v2/invoke", json={**body, "input": inp})
            response.raise_for_status()
            payload = response.json()
            result = payload["result"]
            assert result["status"] == status, payload
            assert result["subtotal_minor"] == subtotal, payload
            assert result["demo"] is True and result["reservation_created"] is False
            assert result["order_created"] is False
            receipt = payload["receipt"]
            signer = Signer(ROOT / ".runtime" / "hub_key")
            assert signer.verify_receipt_signature(receipt), payload
            assert receipt["price_usd"] == 0
            print(f"PASS: Hub -> adapter -> n8n: {status}; subtotal={subtotal}; signed free receipt")
        for inp in ({"items": []}, {"items": [{"sku": "MUG-BLUE", "quantity": -1}]},
                    {"items": [{"sku": "MUG-BLUE", "quantity": 1.5}]}):
            response = client.post("http://127.0.0.1:13456/invoke", json={**body, "input": inp},
                headers={"X-AIMarket-Internal-Token": os.environ["AIMARKET_CAPABILITY_TOKEN"]})
            assert response.status_code == 422, response.text
        print("PASS: invalid quantities and empty cart rejected")
        def rpc(method, params):
            response = client.post("http://127.0.0.1:19083/mcp", json={
                "jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                headers={"Accept": "application/json, text/event-stream"})
            response.raise_for_status()
            if response.headers.get("content-type", "").startswith("text/event-stream"):
                envelope = next(json.loads(line[5:].strip()) for line in response.text.splitlines()
                                if line.startswith("data:"))
            else:
                envelope = response.json()
            assert "error" not in envelope, envelope
            result = envelope["result"]
            assert not result.get("isError"), result
            return result
        tools = rpc("tools/list", {})["tools"]
        assert {"market_search", "market_invoke"} <= {t["name"] for t in tools}
        search = rpc("tools/call", {"name": "market_search", "arguments": {
            "intent": "order check stock", "budget": 0}})
        assert "store.order_check@v1" in json.dumps(search), search
        mcp = rpc("tools/call", {"name": "market_invoke", "arguments": {**body, "max_price_usd": 0}})
        mcp_payload = json.loads(mcp["content"][0]["text"])
        assert mcp_payload["output"]["subtotal_minor"] == 3430, mcp_payload
        assert mcp_payload["output"]["demo"] is True
        print("PASS: MCP tools/list, market_search and market_invoke through the real n8n workflow")
        (ROOT / ".runtime" / "last-result.json").write_text(json.dumps(payload, indent=2) + "\n")
        print("All HTTP checks passed. No external federation, payment, reservation or order was used.")
