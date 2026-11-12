#!/bin/bash
# usage: live_hashes.sh <container>  — prints sha256[:12] of the changed files inside it
c=$1
docker exec -i "$c" python - <<'PY'
import hashlib, importlib, pathlib
files = """aimarket_hub/api.py
aimarket_hub/api_models.py
aimarket_hub/hub_routes/invoke.py
aimarket_hub/hub_routes/invoke_parts/federated_delivery.py
aimarket_hub/hub_routes/invoke_parts/local_delivery.py
aimarket_hub/hub_routes/verification.py
aimarket_hub/mcp_gateway.py
aimarket_hub/receipt_binding.py
aimarket_provenance/plugin.py
aimarket_provenance/receipt.py""".split()
roots = {}
for pkg in ("aimarket_hub", "aimarket_provenance"):
    try:
        roots[pkg] = pathlib.Path(importlib.import_module(pkg).__file__).parent.parent
    except Exception as exc:
        roots[pkg] = None
for f in files:
    root = roots[f.split("/")[0]]
    p = root / f if root else None
    print((hashlib.sha256(p.read_bytes()).hexdigest()[:12] if p and p.exists() else "MISSING     "), f, str(p) if p else "")
PY
