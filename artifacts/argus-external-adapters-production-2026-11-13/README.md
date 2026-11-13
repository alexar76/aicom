# ARGUS external x402 adapters, November 13, 2026

The production images contain the CMC, Tavily and Laso adapter code. The overlays add CoinMarketCap receipt recovery, Laso wallet-based SIWx authentication and mandatory exact approval for built-in paid actions. The deployment preserved the running service configuration and wallet opt-ins.

| Instance | ARGUS | Image | Docker health |
| --- | --- | --- | --- |
| Attested live | 0.3.6 | `sha256:6a4da6b760a693b12b4fb1794980c3ad1d792f2b5a23251784c7590c2d68b1a2` | healthy, 0 restarts |
| Factory live | 0.3.4 | `sha256:8e9878daeb8a761fdddd4a1ba5784dca5e268b53e0bc29c85500adeba5bedc19` | healthy, 0 restarts |
| Factory UNI | 0.3.4 | `sha256:a018b7a687d1f15a45afb61e132f58cdea296d476ece18aa08ac513a3e2c7a4d` | healthy, 0 restarts |

Factory's first overlay brought the three adapters from `d6a77ce9f` onto its existing images and dependencies. Attested already carried those source files. The second overlay updated seven compiled modules and source maps. The third overlaid the two CMC settlement modules and source maps on the running images. Docker builds used `--network none` and candidate smoke tests ran without network access. Before and after recreation, the Docker configuration projection covered environment, entrypoint, command, user, work directory, mounts, port bindings, capabilities, security flags, restart policy and network attachments. All three loopback health responses showed one connected MCP service and zero blocked or failed.

- [Attested rollout log](attested-v3.log)
- [Factory live and UNI rollout log](factory-v3.log)
- [Attested owner boundary](attested-owner-boundary.json)

The fourth overlay changed only the compiled external-payment module and its source map. It sets the SDK's spending cap from the validated request ceiling. Offline tests in each candidate image signed exactly 5 USDC for the pinned Laso recipient, validated a standard Base receipt, and rejected a quote differing by one atom or with a different recipient before sending a signed request. Docker runtime configuration matched before and after the release. Attested still listed CMC as its sole enabled external paid vendor, with exact owner confirmation and a 0.01 USDC signer balance. [Attested fourth rollout](attested-v4.log), [Factory fourth rollout](factory-v4.log), [Attested post-release activation check](attested-cmc-after-laso-v4.json)

The CMC fallback requires a 2xx response with `PAYMENT-RESPONSE` reporting success, a fixed CMC GET and an operator-pinned recipient. It uses a well-formed provider `txHash` as a hint for a direct Base receipt read. A missing hash allows a bounded scan by nonce. The read-only lookup must find the EIP-3009 nonce and immediately following USDC transfer to the quoted recipient for the exact amount in a canonical successful receipt with two confirmations. The deployed reader verified both existing 0.01 USDC transactions. The hash path rejected a wrong nonce without a log scan. The no-hash path rejected a one-atom amount mismatch. [Read-only chain proofs](attested-cmc-v3-proof.ndjson)

The offline candidate tests exercised default-deny, `/yes` rejection, non-owner and group rejection, one-use private Telegram approval and exact execution of the selected tool. They also covered live versus UNI and test mode, Laso merchant quote registration without a static ID token, and delivery of a complete CMC quote through the proprietary receipt path. Local `npm test` passed 524 tests with 10 skipped. `npm run build` and 57 focused tests passed.

The first automatic review rejected persistent signer installation. After the user explicitly approved permanent CMC activation in private Telegram, automatic review allowed the dedicated signer installation. The installer read the key over SSH stdin into root-only mode `0600`, verified that only two live ARGUS environment fields changed, and preserved the UNI Compose configuration. The restarted Attested service exposes `cmc_buy_quotes` to the pinned owner at `@Argis3Bot` with exact approval. An unapproved call made zero provider requests, public `/ask` returned 503 and the signer balance remained 0.01 Base USDC. [Activation verification](attested-cmc-activation.json), [Telegram startup](attested-cmc-telegram-status.json), [restart log](attested-cmc-activation.log)

Rollback copies for the fourth rollout are on their respective hosts at `/root/argus/docker-compose.roster.yml.pre-vendors-v4-20261113` and `/root/claudecode/aicom/argus/docker-compose.yml.pre-vendors-v4-20261113`.
