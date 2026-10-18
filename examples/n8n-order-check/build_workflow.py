"""Generate importable n8n workflow from the version-controlled Code node."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
workflow = {
    "id": "aimarketOrderCheckWorkshop",
    "name": "Workshop — read-only order check (synthetic catalogue)",
    "active": False,
    "nodes": [
        {"id": "receive", "name": "Receive cart", "type": "n8n-nodes-base.webhook",
         "typeVersion": 2, "position": [0, 0], "webhookId": "aimarket-order-check",
         "parameters": {"httpMethod": "POST", "path": "aimarket-order-check",
                        "authentication": "headerAuth", "responseMode": "responseNode", "options": {}},
         "credentials": {"httpHeaderAuth": {"id": "aimarketWorkshopWebhook", "name": "Workshop webhook secret"}}},
        {"id": "quote", "name": "Check synthetic catalogue", "type": "n8n-nodes-base.code",
         "typeVersion": 2, "position": [240, 0],
         "parameters": {"mode": "runOnceForAllItems", "jsCode": (ROOT / "quote.js").read_text()}},
        {"id": "reply", "name": "Return result", "type": "n8n-nodes-base.respondToWebhook",
         "typeVersion": 1.4, "position": [480, 0],
         "parameters": {"respondWith": "json", "responseBody": "={{ $json.body }}",
                        "options": {"responseCode": "={{ $json.statusCode }}"}}},
    ],
    "connections": {
        "Receive cart": {"main": [[{"node": "Check synthetic catalogue", "type": "main", "index": 0}]]},
        "Check synthetic catalogue": {"main": [[{"node": "Return result", "type": "main", "index": 0}]]},
    },
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none",
                 "saveDataErrorExecution": "none", "saveManualExecutions": False},
    "pinData": {},
}
if __name__ == "__main__":
    (ROOT / "workflow.json").write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n")
