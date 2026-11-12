# Unity MCP 10.3.0 tool list baseline

HISTOR recorded **48 tools and 23,686 tokens** for the published Unity MCP 10.3.0 package over stdio without an Editor. The three versioned observations on October 28, November 2 and November 8, 2026 have the same tool-set digest. Input schemas account for 15,941 tokens, about 67% of the counted list. This makes schema growth a useful CI check even when a release adds no tool names. [HISTOR observation](https://histor.modelmarket.dev/s/c92ce8ceb0ed7dbd) · [Upstream issue #1482](https://github.com/CoplayDev/unity-mcp/issues/1482)

## Evidence

The upstream issue remained open and 10.3.0 was the stable release on November 11. The wheel retrieved from PyPI matches both the publisher's SHA-256 and the integrity value stored by HISTOR. The archived tool list is a complete array from the immutable tool-set endpoint. The latest versioned observation used the `mcp-for-unity` entry point in a Python 3.12 gVisor sandbox, with MCP protocol `2025-06-18` and `serverInfo.version` `3.4.11`. [Release](https://github.com/CoplayDev/unity-mcp/releases/tag/v10.3.0) · [PyPI wheel provenance](https://pypi.org/project/mcpforunityserver/10.3.0/#files) · [Capture metadata](observation.json) · [Archived array](unity-10.3.0-tools.json)

| Measure | Tokens |
| --- | ---: |
| Compact JSON of `name`, `description`, `input_schema` | 23,686 |
| Input schemas | 15,941 |
| Descriptions | 7,277 |
| Names | 217 |
| Keys and punctuation | 251 |
| Output schemas, counted separately | 1,941 |
| Whole archived array including output schemas | 25,770 |

The largest tools in the counted projection were `manage_physics` (2,140), `manage_graphics` (1,719), `manage_camera` (1,453), `manage_probuilder` (1,143) and `manage_ui` (1,067). Their individual counts sum to about 32% of the projected list. Counts use `o200k_base` in `tiktoken==0.14.0`. A client that selects tools, adds wrappers, or uses a different chat template will have its own prompt token count. [HISTOR count specification](https://github.com/alexar76/histor/blob/main/docs/tool-list-cost.md)

The October 20 matrix below was reported in the upstream issue for the packaged server and Unity 2022.3.62f3 on Windows, in a clean project with default tool toggles. It counts the whole tool array with `o200k_base`. The local archived observation covers the stdio row without Editor and uses the compact projection above. The three other cases still need captured lists under the same counting rules. [Original measurement and setup](https://github.com/CoplayDev/unity-mcp/issues/1482#issuecomment-6284764818)

| Upstream setup | Tools | Reported tokens |
| --- | ---: | ---: |
| HTTP without Editor | 29 | 16,392 |
| HTTP with Editor | 48 | 27,927 |
| stdio without Editor | 48 | 27,927 |
| stdio with Editor | 48 | 27,927 |

## Run the offline check

From the directory containing this README, install the pinned counter in a Python 3.12 environment and run the verifier. After the first tokenizer cache fill, the verification uses only local files. The script validates the byte hash and MTL/1 digest, then runs the published CLI against the archive. The CLI returns 0 for the unchanged list, and 1 for the generated test case adding 64 artificial fields to `manage_physics`. Those fields increase the schema total by 1,664 tokens (10.4%) while the total projected list grows by 7.0%. This demonstrates the independent 10% schema gate. [Verifier](verify.py) · [Verification output](verification.json)

```sh
python -m pip install 'aimarket-histor[cost]==0.8.0' 'tiktoken==0.14.0' 'rfc8785==0.1.4'
python verify.py
```

To use the known stdio capture as a baseline for an equivalent run, pass the new complete tool list to the same CI command. The 10% threshold is an example. Review changes to tool availability and the chosen thresholds with the release. [HISTOR CI example](https://github.com/alexar76/histor/blob/main/examples/tool-cost/README.md)

```sh
python -m histor tool-cost snapshot --tools unity-10.3.0-tools.json -o baseline-stdio-no-editor.json
python -m histor tool-cost check --baseline baseline-stdio-no-editor.json \
  --tools candidate-stdio-no-editor.json --max-increase 10% --noise 50
```

## Capture the transport and Editor matrix

Use a fresh project with the Unity plugin at `v10.3.0`. Use the same Editor version, project, tool toggles, dependency lock and tool scope across cases. Keep the no-Editor run separate. For a connected run, record the session or registration log confirming the Editor before sampling. Save the transport, platform, package and plugin versions, dependency lock, negotiated MCP version and whether the list was complete next to each snapshot. The examples pin the Unity MCP and FastMCP packages for the operator who has the environment. The reported November capture used HISTOR's own sandbox image and dependencies. [Upstream install and transport options](https://pypi.org/project/mcpforunityserver/10.3.0/#description)

For stdio, repeat the command once with the Editor closed and once after configuring its stdio bridge. Use `stdio-editor.json` for the connected output.

```sh
python -m histor tool-cost snapshot --timeout 30 \
  --stdio 'uvx --from mcpforunityserver==10.3.0 --with fastmcp==3.4.11 mcp-for-unity --transport stdio' \
  -o stdio-no-editor.json
```

For HTTP, run the loopback server in one terminal, then measure from a second terminal. Configure the Editor to use that loopback address for the connected sample and write it to `http-editor.json`.

```sh
uvx --from 'mcpforunityserver==10.3.0' --with 'fastmcp==3.4.11' \
  mcp-for-unity --transport http --http-url http://127.0.0.1:18080
```

```sh
python -m histor tool-cost snapshot --timeout 30 --url http://127.0.0.1:18080/mcp -o http-no-editor.json
python -m histor tool-cost diff http-no-editor.json http-editor.json
```

These commands measure advertised definitions using `tools/list`. For a model-facing budget, pair them with a recording of the same client's model request and the provider's usage fields. The archived Unity definitions retain the upstream MIT notice. [CoplayDev license](LICENSE-CoplayDev.txt)
