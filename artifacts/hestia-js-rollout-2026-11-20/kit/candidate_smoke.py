import json, sys
from hestia.sandbox import Sandbox
req = json.load(sys.stdin)
box = Sandbox(memory_mb=256, timeout_s=10.0)
out = {"languages": box.languages}
out["python"] = box.run("def handle(p):\n    return {'n': len(p)}\n", {"a": 1, "b": 2}).to_json()
out["js"] = box.run("async function handle(p) { return {sum: p.a + p.b}; }", {"a": 2, "b": 3}, language="javascript").to_json()
out["js_escape"] = box.run("async function handle(){ const m = await import('qjs:std'); return {p: m.loadFile('/data/provider.key'), e: m.getenviron()}; }", {}, language="javascript").to_json()
w = box.run(req["warden"], req["probe"], language="javascript").to_json()
out["warden"] = {"kind": w["kind"], "verdict": (w.get("result") or {}).get("verdict"), "codes": [f["code"] for f in (w.get("result") or {}).get("findings", [])], "ruleset": (w.get("result") or {}).get("ruleset"), "warden": (w.get("result") or {}).get("warden"), "ms": w["wall_ms"], "error": w.get("error")}
box.close()
print(json.dumps(out))
