A tool's description can shrink while its schema grows. A single token total can hide that regression. Here is a complete example that checks the total, descriptions and input schemas separately, then shows how to use the same check in your existing CI job.

**AI disclosure:** AI agents prepared this example, its verification and this article under the project owner's direction. I maintain HISTOR in the alexar76 ecosystem. This is our own reproducibility check; it is not evidence that an external team has adopted the CI check.

[Raju asked for a CI check](https://dev.to/alexar76/what-an-mcp-servers-tool-list-costs-we-counted-the-tokens-of-34374-of-them-3011#comment-3ij29) after our tool-definition cost survey. This page includes every command and the complete fetch script, so it can be used without a repository checkout.

## The real change used in the example

[HISTOR change 28848](https://histor.modelmarket.dev/api/v1/changes/28848/cost) records a change to textokit's remote MCP endpoint observed on 24 October 2026 at 19:52 UTC. Its before and after lists both have 20 tools; 17 definitions changed. We count compact `{name, description, input_schema}` definitions with `o200k_base`.

| Tokens | Before | After | Change |
| --- | ---: | ---: | ---: |
| Full definitions in the counted model-input form | 5,565 | 3,776 | -1,789 / -32.1% |
| Descriptions | 2,158 | 783 | -1,375 |
| Input schemas | 3,165 | 2,751 | -414 |
| Names | 120 | 120 | 0 |
| Keys and punctuation | 122 | 122 | 0 |

This is an observed remote definition change. It does not establish which npm release deployed it or imply an endorsement. The reproduction below downloads stored definition data. It does not run textokit code, call its tools or buy a service.

## 1. Create an isolated working directory

Use Python 3.11. The example pins the published CLI and tokenizer versions rather than depending on the current latest release.

```sh
mkdir -p /tmp/histor-tool-cost-demo
cd /tmp/histor-tool-cost-demo
python3.11 -m venv .venv
. .venv/bin/activate
python -m pip install 'aimarket-histor[cost]==0.3.1' 'tiktoken==0.14.0'
```

Installation, fetching the public lists and initially populating the tokenizer cache require network access. The recorded token-count validation itself ran without network access on a Linux server with Python 3.11.2 and tiktoken 0.14.0.

For precise provenance: those CLI checks ran in a HISTOR 0.4.0 container. We separately verified that its `histor/toolcost.py` and `histor/toolcost_cli.py` bytes are identical to the published 0.3.1 wheel used in the command above. This is not a claim of a separate fresh end-to-end installation test of that entire published wheel.

## 2. Save and run the complete fetch script

Copy this shell block into the same directory. It writes `fetch_textokit.py` in full:

```sh
cat > fetch_textokit.py <<'PY'
"""Fetch the immutable public tool lists of HISTOR change 28848; execute no server tools."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.parse
import urllib.request

from histor.subject import tool_set_digest

SNAPSHOTS = {
    "before": "sha256-IP5W+kYoXogt7RDDPbG0FmUE97uEAqyIdxDoPjuocUA=",
    "after": "sha256-zIV5QNaJd0IQp+5yFiYc4gtjQVAtMjfSc3Kq2tcE5uc=",
}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for name, digest in SNAPSHOTS.items():
        url = "https://histor.modelmarket.dev/api/v1/toolsets/" + urllib.parse.quote(digest, safe="")
        request = urllib.request.Request(url, headers={"User-Agent": "HISTOR-cost-example/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
        if len(raw) > 4 * 1024 * 1024:
            raise ValueError("tool list exceeds the example's size limit")
        tools = json.loads(raw)
        if not isinstance(tools, list):
            raise ValueError("expected a tool array")
        actual, _ = tool_set_digest(tools)
        if actual != digest:
            raise ValueError(f"digest mismatch for {name}: {actual}")
        (args.out / f"{name}-tools.json").write_text(json.dumps(tools, ensure_ascii=False, indent=2) + "\n")
        print(f"{name}: {len(tools)} tools, {actual}")


if __name__ == "__main__":
    main()
PY
```

Then fetch the pair:

```sh
python fetch_textokit.py --out /tmp/textokit-cost
```

The script checks HISTOR's canonical tool-set digest for each list, not the SHA-256 of a particular JSON serialization. It refuses a changed digest or an oversized response. Both lists should contain 20 tools. No API key is required.

## 3. Run the passing check

```sh
histor tool-cost snapshot \
  --tools /tmp/textokit-cost/before-tools.json \
  -o /tmp/textokit-cost/baseline.json

histor tool-cost check \
  --baseline /tmp/textokit-cost/baseline.json \
  --tools /tmp/textokit-cost/after-tools.json \
  --max-increase 10%
```

Expected exit code: **0**. The total, descriptions and input schemas all became smaller. They are gated separately: shorter descriptions cannot conceal a large schema increase in the aggregate.

## 4. Prove the gate can fail

Deliberately compare the same lists in the opposite direction:

```sh
histor tool-cost snapshot \
  --tools /tmp/textokit-cost/after-tools.json \
  -o /tmp/textokit-cost/reduced-baseline.json

histor tool-cost check \
  --baseline /tmp/textokit-cost/reduced-baseline.json \
  --tools /tmp/textokit-cost/before-tools.json \
  --max-increase 10%
```

Expected exit code: **1**, with three reported problems:

- Full definitions: +1,789 tokens / +47.4%.
- Descriptions: +1,375 / +175.6%.
- Input schemas: +414 / +15.0%.

This simulates returning to the older, larger definitions. It does not claim that a later textokit release regressed. Exit **2** means the input could not be obtained or counted, rather than a successful comparison. Growth below the default 50-token noise floor does not fail the gate; `--noise` can change that policy.

## 5. Add the check to your own server's CI

After building your own server, create a baseline once and commit the JSON file:

```sh
histor tool-cost snapshot --stdio 'node dist/index.js' -o tool-cost.json
```

Use your actual launch command. Unlike the stored-list example, `--stdio` launches your server and requests `initialize` and `tools/list`.

In a CI job that already installs dependencies and builds your project, add these steps:

```yaml
- name: Install the pinned tool-cost checker
  run: |
    python3.11 -m venv .venv-tool-cost
    .venv-tool-cost/bin/python -m pip install 'aimarket-histor[cost]==0.3.1' 'tiktoken==0.14.0'

- name: Check tool-definition growth
  run: |
    .venv-tool-cost/bin/histor tool-cost check \
      --baseline tool-cost.json \
      --stdio 'node dist/index.js' \
      --max-increase 10%
```

The runner needs Python 3.11 and the runtime your server uses. If your build already exports `tools/list`, replace `--stdio 'node dist/index.js'` with `--tools current-tools.json`. The command also writes its Markdown table to the job summary when `GITHUB_STEP_SUMMARY` is present.

Review changes to the committed baseline when accepting growth. Do not regenerate it immediately before every CI check: that would compare the new list with itself. Keep tokenizer and CLI versions fixed on both sides of a baseline comparison; review and regenerate the baseline explicitly when changing them.

## What the number means

The check counts complete definitions in one documented input form. Clients that load tools on demand may send only a subset. Provider wrappers add tokens, and prompt-cache writes and reads have different billing rules. Actual invoices require the client's usage records.

The useful CI signal is bounded: a reviewed definition baseline changed enough to exceed your chosen limits. It does not judge tool quality, security or whether a larger schema is justified.
