"""Run one bounded authenticated Metis agent request inside its container."""

import hashlib
import json
import os
import urllib.error
import urllib.request

endpoint = "https://metis.modelmarket.dev/v1/chat/completions"
key = next(os.environ[name] for name in ("METIS_API_KEY", "SUPERBRAIN_API_KEY", "COGNITIVE_API_KEY") if os.environ.get(name))
query = (
    "Use the web_search tool exactly once to look up RFC 9110 section 15.5.3. "
    "Then answer in one short sentence what HTTP 402 means. Include the source URL only if it appeared in the tool output."
)
body = json.dumps({"model": "metis-agent", "messages": [{"role": "user", "content": query}]}).encode()
request = urllib.request.Request(endpoint, data=body, headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})

try:
    with urllib.request.urlopen(request, timeout=95) as response:
        status = response.status
        result = json.load(response)
except urllib.error.HTTPError as error:
    print(json.dumps({"http": error.code, "endpoint": endpoint}))
    raise SystemExit(1) from None
except (OSError, ValueError) as error:
    print(json.dumps({"error_type": type(error).__name__, "endpoint": endpoint}))
    raise SystemExit(1) from None

choice = result["choices"][0]
answer = choice["message"]["content"]
print(json.dumps({
    "endpoint": endpoint,
    "http": status,
    "id": result.get("id"),
    "model": result.get("model"),
    "finish_reason": choice["finish_reason"],
    "answer_sha256": hashlib.sha256(answer.encode()).hexdigest(),
    "answer_mentions_payment_required": "payment required" in answer.lower(),
    "answer_mentions_reserved": "reserved" in answer.lower(),
    "answer_has_url": "https://" in answer,
    "usage": result.get("usage"),
}))
