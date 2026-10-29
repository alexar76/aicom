# Localhost authentication article: fact check

Checked on 28 October 2026. The wheel facts below come from the earlier public-read tool result in this chat: both wheels were downloaded into memory, checked against PyPI SHA-256, and inspected with `zipfile`. They were not installed, imported or executed. No network requests were repeated while saving these notes. Exact metadata and hashes are in `wheel-inspection.json`.

## Verified release comparison

- **aimarket-mcp 0.6.3:** `server.py` allows a keyless, non-public, non-production RPC request only through its local-client checks. The Linux socket owner check accepts a socket owned by the server's UID. When neither `/proc/net/tcp` nor `/proc/net/tcp6` exists, `_caller_is_this_user` returns `True`. A same-user local proxy therefore passes the identity inference described by [Vulnetix 000640](https://github.com/Vulnetix/advisory-database/blob/main/cvelistv5/VULN-PYPI/2026/0xxx/GCVE-110-VULN-PYPI-2026-000640.json).
- **aimarket-mcp 0.6.4:** keyless RPC POST is denied by default, including loopback connections owned by the server's user. `AIMARKET_MCP_LOCAL_RELAY=1` explicitly enables trusting local TCP relays; if the Linux socket tables are absent, `AIMARKET_MCP_LOCAL_UNVERIFIED=1` is also required. Existing peer, Host, Origin, forwarding-header and available socket-owner checks still apply in this opted-in branch.
- A configured `AIMARKET_MCP_KEY` requires the matching HTTP Bearer value. The key is supplied by the operator before starting the process; the package does not generate one automatically.
- PyPI published the 0.6.4 wheel at **2026-10-28 10:38:15 UTC / 13:38:15 Moscow**. Its `aimarket_mcp/server.py` is byte-identical to the local source inspected in this task.

Local source anchors: `aimarket-mcp/aimarket_mcp/server.py:34`, `:162`, `:215`, `:299`. Regression definitions: `aimarket-mcp/tests/test_gateway.py:206` and `:223`; cross-package synthetic socket-owner cases: `tests/test_keyless_tcp_authorization.py:149`. These tests were read, not run by this fact-check task.

## Required limits on article claims

- Describe authentication of **HTTP RPC POST**, not every HTTP request. `/health` stays public; MCP stdio is unchanged.
- Explicit `AIMARKET_MCP_PUBLIC=1` allows anonymous RPC even with production enabled when no key is configured. It does not override a configured Bearer key. See `aimarket-mcp/tests/test_hosted.py:240` and `:248`.
- The saved Vulnetix record still has state PUBLISHED and lists affected versions through 0.6.3 with `defaultStatus=unknown`; it does not list 0.6.4 as fixed. Do not claim Vulnetix independently verified or closed the new release.
- The startup warning at `server.py:436` still describes the older behavior. Use the executable gate and documented settings as evidence, not that warning.
- The changelog mentions removal of process-name/listener heuristics. Those were an intermediate local attempt, not present in the published 0.6.3 wheel inspected here. Do not describe their removal as a 0.6.3-to-0.6.4 release difference.
- A Bearer credential proves possession of that credential, not a person's identity or safety against a compromised process that can read the credential. Loopback binding remains useful, but it does not identify the original caller behind a relay.

## Static review of the educational demonstration

Read `localhost_auth_demo.py` in full without running or changing it. It matches the stated bounded demonstration:

- All listeners bind IPv4 `127.0.0.1` with ephemeral ports; every client and upstream connection also uses `127.0.0.1`.
- The relay has a fixed upstream and `/private` path. It does not take a destination URL from the caller.
- The relay forwards an Authorization header only when the caller supplied one; it never injects the valid backend key for anonymous callers.
- The demonstration generates a fresh synthetic key locally with `secrets.token_urlsafe(32)`. Requests and credentials are not logged, and the key is not included in the result JSON.
- The matrix has two peer-only cases and six Bearer cases: direct/relay with no key, wrong key and valid key as applicable. Assertions check status, accepted state and the backend's loopback peer address.
- It is a standard-library HTTP reconstruction, not an execution of the MCP package, a Linux UID test, a remote-exploit reproduction, or proof that all production configurations are fixed. Direct and relayed requests have different ephemeral source ports; the demonstrated common property is the loopback source address.

No source or demonstration files were changed by this fact-check. Only these technical notes and their JSON metadata were saved.
