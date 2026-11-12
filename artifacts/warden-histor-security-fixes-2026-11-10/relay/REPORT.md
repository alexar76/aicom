# AgentDojo relay redirect fix — 10 November 2026

`warden/scripts/agentdojo/relay.py` now validates its operator-selected endpoint before reading the API key. Only HTTPS URLs with a hostname and valid port are accepted; URL credentials, fragments, control characters and whitespace are rejected with a generic error that does not echo the supplied URL. A dedicated urllib opener refuses every redirect, including cross-origin HTTPS, HTTPS-to-HTTP and same-origin redirects. Authorization is sent only to the explicitly selected endpoint. The existing success, HTTP error reporting, rate-limit/transient-error retry and budget-accounting paths remain in place.

Added `warden/scripts/agentdojo/test_relay.py`. These tests exercise the actual `main` request/reply path and urllib redirect handler, while in-memory transports intercept all HTTP(S) requests. They use a dummy credential, no sockets, no model call and no paid API.

Verification:

- **24 passed** in `tests.log`: 15 redirect cases (301/302/303/307/308 × cross-origin HTTPS, HTTP downgrade and same-origin), normal HTTPS success, 429 retry followed by success, and seven invalid endpoint cases rejected before key loading.
- The three 302 boundary cases **fail against the original source**, preserved as a negative control in `pre-fix-control.log` / `pre-fix-control.json`. They observe a second redirected request. This demonstrates the tests catch the original behavior; these expected control failures are not unfixed current-code failures. The baseline files are historical test evidence, not active source.
- Scoped Ruff and `git diff --check` passed. No JavaScript/runtime dependency changes were made, so the previously recorded Warden runtime suite was not repeated for this Python-only research-tool fix.

The fix applies to this local source only. It does not change a running research relay or previously copied container/host context. No publication, GitHub write or deployment occurred. Other agents own the independent shell/Histor fixes.
