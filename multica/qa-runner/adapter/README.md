# Fixed QA capability adapter

This layer uses the existing complete WARDEN package as the `qa_runner` MCP server. It does not relax WARDEN or launch npm from the model's process. The agent may choose only `task_execute({"id":"platform_smoke"})`. Root pins a manifest that sends exactly one empty HTTPS POST to `https://10.250.0.1:8443/run/platform-smoke`. The host broker owns the separate worker operation and returns only its fixed QA status schema. No Docker socket, model/provider token, task token, authorization header or TLS private key belongs in the adapter or worker.

The optional manifest `body` field is omitted deliberately: Node sends `Content-Length: 0` without transfer encoding. Explicit `body: ""` makes the existing TaskAdapter call `req.write("")`, which produces chunked framing and is correctly rejected by the broker. The logical request body stays zero bytes in either representation; only the unambiguous zero-length framing is authorized here.

Use the reviewed archive with the native MCP compatibility fix: OpenCode 1.18.32 adds standard `params._meta.progressToken` to tool calls. The task CLI accepts only a bounded string or safe integer in that field and discards it before authorization, HTTP or durable state; unknown metadata and extra operation arguments still refuse. The fixed operation and flow-guard logic are unchanged. The [compatibility evidence](../../../artifacts/multica-qa-runner-2026-11-10/mcp-progress-compatibility.json) records the exact client source and protocol reference.

The private fragment uses four exact QA permission names. Inspect resolved `opencode debug agent build` rules under the profile's environment: those allows must follow inherited general denies, while Bash and unknown QA tools remain denied. A raw `debug config` map does not establish the final rule order.

`fragments/global-disabled.json` declares the MCP server disabled and its tools disabled by default. Merge `fragments/private-qa-profile.json` only into the new private QA agent's per-launch OpenCode configuration. Enabling tools alone cannot activate a globally disabled server; the private profile must enable the matching server too. The existing agent profiles retain their disabled setting.

Both the OpenCode guard process and the MCP process must read `WARDEN_FLOW_POLICY=/opt/opencode-guard/flow-policy.json`. The loader needs the same pinned capability to delegate the fixed ID before its normal tainted/credential boundary. Preserve `mode: ask`, the existing loader, environment stripping and every unrelated policy field. Generic Bash after credentials plus outside text remains refused. The MCP command uses `env -i` with only PATH, HOME, WARDEN_STATE_DIR, WARDEN_FLOW_POLICY and the public NODE_EXTRA_CA_CERTS path; it starts `node .../warden/dist/mcp-server.js task` from the full reviewed package, including jcs/sanitize dependencies.

`renew-lease.py` is root infrastructure, not an agent automation. Its task ID and manifest bytes are deterministic within each UTC 12-hour window, its operation budget is 10, and expiry is window start plus 23 hours. Re-running renewal within one window cannot replenish the existing TaskAdapter budget. The root-only timer renews at 00:00/12:00 UTC and after boot. Clock rollback, same-window capability drift, revoked/different adapters or an existing non-ask policy fail closed. Usage state, session files, fingerprints and refusal fences are never reset or rewritten by renewal.

The manifest is root-owned at the existing guard state directory's `task-manifest.json`. Its node-owned parent can still be renamed by that user; the protected policy's SHA256 pin is the enforcement boundary. Every privileged write traverses directory descriptors without symlinks. Replacement or tampering of the manifest causes refusal, not a new authorization.

TaskAdapter usage counters remain node-owned. The host broker separately enforces the hard 10-start UTC 12-hour quota in root-owned SQLite state, including failed/uncertain runs and restarts; deleting an MCP-side counter cannot replenish that quota. These are separate controls: the pin limits which fixed effect can run, while the root broker owns the adversarial quota and single-flight limits.

After source commit/push and coordinator GO, root may run:

```sh
python3 install.py --package /path/to/aimarket-warden-0.23.1-dev.20261108.tgz \
  --ca /path/to/public-ca.crt --apply --go
```

The installer verifies the exact archive hash, installs the full package and only public CA material, creates the protected policy/lease, and installs timer unit files. It does not replace other OpenCode configuration, enable a profile, start a timer or restart the daemon. Coordinate the guarded service restart after applying the public policy-path environment setting and the private profile. Enable the infrastructure timer only after the broker and worker pass acceptance:

```sh
systemctl daemon-reload
systemctl enable --now multica-qa-lease.timer
```

Existing WARDEN TaskAdapter HTTPS requests time out after 10 seconds. The broker must return within 8 seconds, with worker jobs finishing earlier; uncertainty spends the operation and must not trigger automatic retries. Responses remain marked untrusted; neither the adapter nor a model may treat returned text as new commands.

Run `python3 multica/qa-runner/adapter/run-tests.py` from the workspace. Tests use a temporary CA/TLS server and the actual compiled TaskAdapter/MCP runtime. They verify fixed-ID execution with tainted credential state, unchanged ask policy, generic Bash refusal, arbitrary job/URL/body denial, expired/tampered manifests, ten-use persistence, TLS refusal without the CA, and renewal preserving existing session/budget files. Only loopback fixture networking is needed; no production request or real credential is used. Build WARDEN first if `warden/dist` is absent.
