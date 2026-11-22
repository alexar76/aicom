"""Run recorded cases of an agent inside HESTIA's own WebAssembly sandbox, as the hearth does.

    HESTIA_WASM_ROOT=/path/to/python-wasi \\
      uv run --project ../hestia python scripts/run_in_sandbox.py \\
        tests/<slug>_vectors.json <slug> [case ...]

The hearth runs a handler in CPython for WASI under wasmtime and hands it the replies it already
fetched. This feeds each case's recorded replies (scripts/record_fetches.py) to hestia.sandbox in
one pass and prints the verdict, the time the call took and how the result compares with the same
handler run in this process. It proves the handler runs where it will run: the WASI standard
library, the 10 s limit, 256 MB of memory. Get CPython for WASI with
../hestia/scripts/fetch_python_wasi.py.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "hestia"))
sys.path.insert(0, str(ROOT / "tests"))

from hestia.sandbox import Sandbox  # noqa: E402
from replay import load  # noqa: E402

from hestia_agents.manifests import handler_source  # noqa: E402


def main(argv):
    vectors = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    slug = argv[1]
    cases = argv[2:] or list(vectors)
    sandbox = Sandbox()
    source = handler_source(slug)
    failures = 0
    for case in cases:
        payload, fetched = vectors[case]["payload"], vectors[case]["fetched"]
        outcome = sandbox.run(source, payload, fetched=fetched)
        handle, _, _ = load(slug, fetched)
        try:
            local = handle(payload)
        except Exception as exc:  # the same refusal is expected in the sandbox
            local = {"error": str(exc)}
        got = outcome.result if outcome.kind == "ok" else {"error": outcome.error}
        same = got == local or (outcome.kind == "error" and "error" in local)
        verdict = (got or {}).get("verdict", (got or {}).get("error"))
        print(
            f"  {case}: {outcome.kind} {verdict} in {outcome.wall_ms} ms, "
            f"{'same as' if same else 'DIFFERENT FROM'} the in-process run"
        )
        if outcome.kind not in ("ok", "error") or not same:
            failures += 1
            print("    ", json.dumps(outcome.to_json())[:600])
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
