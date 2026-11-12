# PayPal MCP `tools/list` replay

On 2026-11-11, the published `@paypal/mcp` 1.8.1 CLI and `@paypal/agent-toolkit` 1.11.0 returned different `list_transactions` schemas in two requests to the same process and again after restart. The replay exposed only `transactions.list` and used the published package with the dependency tree in [package-lock.json](package-lock.json), including MCP SDK 1.32.2. The protocol negotiated was `2025-03-26`. [PayPal issue #120](https://github.com/paypal/agent-toolkit/issues/120) · [PayPal local MCP documentation](https://developer.paypal.com/ai-tools/mcp-server#local-mcp-server)

| Process / request | `start_date.default` (UTC) | `end_date.default` (UTC) |
| --- | --- | --- |
| 1 / 1 | `2026-10-11T15:01:29.637Z` | `2026-11-11T15:01:29.639Z` |
| 1 / 2 | `2026-10-11T15:01:29.707Z` | `2026-11-11T15:01:29.707Z` |
| 2 / 1 | `2026-10-11T15:01:38.106Z` | `2026-11-11T15:01:38.106Z` |

These are the only two changed fields across all three comparisons. [capture.json](capture.json) contains the three complete `tools` arrays and the isolation checks. [diff.json](diff.json) contains their SHA-256 digests and exact JSON Pointer changes. The pinned toolkit uses clock-dependent Zod defaults for both fields, and the serialized listing contains the resulting timestamps. The measured scope was the schema of one tool. A client that includes the full definitions in a cache key can get different keys from these responses. Cache hits, token usage and PayPal API behavior were outside the replay scope.

## Run the replay

Run from this directory with Node.js 22, npm and Docker. The command uses the locally cached `linux/arm64` Node 22.23.4 image by its image ID. On another architecture, select the local image ID for that platform. The npm step downloads the lockfile's artifacts from the public registry with lifecycle scripts disabled. The container then runs the CLI twice with a synthetic token, an explicit sandbox argument and stdio JSON-RPC. The only methods sent are `initialize`, `notifications/initialized` and `tools/list`.

```sh
replay_dir=$(mktemp -d /private/tmp/aicom-paypal-mcp-replay.XXXXXX)
chmod 755 "$replay_dir"
cp package.json package-lock.json capture.mjs "$replay_dir/"
(cd "$replay_dir" && npm ci --ignore-scripts --no-audit --no-fund \
  --registry=https://registry.npmjs.org) && \
docker run --rm --pull never --network none --read-only \
  --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --pids-limit 64 --memory 512m \
  --mount "type=bind,source=$replay_dir,target=/replay,readonly" \
  --workdir /replay --entrypoint /usr/local/bin/node \
  sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d \
  capture.mjs > replay-capture.json
node gate.mjs replay-capture.json > replay-diff.json
```

Use `/tmp` in the `mktemp` command on Linux. Before starting the CLI, the harness verifies the container UID, zero effective capabilities, `no-new-privileges`, loopback as the only interface, `ENETUNREACH` for a TCP probe, and `EROFS` for writes to `/tmp` and the replay mount. The first attempt reached the harness's 10-second startup limit on the Docker Desktop bind mount. The successful replay used the 30-second limit in the checked-in harness.

Run `node gate.mjs capture.json` against the saved evidence without installing any packages. The gate exits `0` when all three tool arrays are stable, `1` when a field changes and `2` when the input cannot be parsed or is missing the expected capture structure. It sorts object keys and preserves array order. The recorded evidence returns `1`.
