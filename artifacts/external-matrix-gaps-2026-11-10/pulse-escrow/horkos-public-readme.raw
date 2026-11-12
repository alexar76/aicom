# escrow-policy-signer — HORKOS

<!-- aicom-readme-badges -->
<p align="center">
  <a href="https://github.com/alexar76/escrow-signer/actions/workflows/ci.yml"><img src="https://github.com/alexar76/escrow-signer/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://alexar76.github.io/escrow-signer/"><img src="https://img.shields.io/badge/landing-GitHub%20Pages-9c70ff" alt="Landing" /></a>
  <img src="https://img.shields.io/badge/allowed%20selectors-1-8d83ff" alt="One allowed selector" />
  <img src="https://img.shields.io/badge/chain-Base%208453-0052FF" alt="Base mainnet" />
  <img src="https://img.shields.io/badge/docs-EN%20RU%20ES%20FR%20ZH-9c70ff" alt="5 languages" />
  <img src="https://img.shields.io/badge/python-%3E%3D3.11-3776AB" alt="Python >=3.11" />
  <img src="https://img.shields.io/badge/tests-95-4c1" alt="95 tests" />
  <a href="https://github.com/alexar76/escrow-signer/blob/main/LICENSE"><img src="https://raw.githubusercontent.com/alexar76/escrow-signer/refs/heads/main/docs/badges/license.svg" alt="License: MIT" /></a>
</p>
<!-- /aicom-readme-badges -->

<!-- aicom-mirror-notice -->
> 🔄 Synced from the [AI-Factory monorepo](https://github.com/alexar76/aicom) (append-only history). **Pull requests are welcome** — merged PRs are imported back and re-synced here. [Issues](https://github.com/alexar76/escrow-signer/issues) · [Pull requests](https://github.com/alexar76/escrow-signer/pulls)

<p align="center">
  <strong>HORKOS</strong> (ὅρκος) — the oath, and the punishment for breaking one<br>
  Holds the only key authorized in <code>AIMarketEscrow.authorizedHubs</code>, so the Hub does not
</p>

<p align="center">
  <a href="README.md"><b>English</b></a> ·
  <a href="docs/README.ru.md">Русский</a> ·
  <a href="docs/README.es.md">Español</a> ·
  <a href="docs/README.fr.md">Français</a> ·
  <a href="docs/README.zh.md">中文</a> ·
  <a href="https://alexar76.github.io/escrow-signer/">Landing</a>
</p>

The only process in the ecosystem that holds a key authorized in
`AIMarketEscrow.authorizedHubs`. It exists so that the hub does not.

**Address:** `0xBE0bBE44cceCfEb048dd53f601C37525a3D6C5f1` ·
**Chain:** Base mainnet (8453) · **Escrow:** `0xa4cb6ef73B982B847fB06Ec75540d05D0311B2Eb`
· **Host:** the skopos box (`skopos-host`), reached from the hub host over a reverse SSH
tunnel. Never the hub box: sharing a machine would make "the key never enters the hub
process" a sentence rather than a boundary.

## What it will sign

Exactly one thing: a canonical `debitChannel(bytes32,uint256,bytes32,uint256,bytes)` call,
selector `0xf7becd80`, to the one pinned escrow, on the one pinned chain, with `value == 0`.
Nothing else on request — not `settleChannel`, not an ERC-20 `transfer`, not `setHubAuthorization`,
not a contract creation, not on Sepolia. (The proceeds sweep below is the service's own, never a
caller's.)

The authority for the **amount** is not the hub. It is the depositor's EIP-712 signature,
re-verified here against channel state this service read itself, with **our own address**
substituted for the `hub` field — exactly as the contract does. A signature minted for
another hub, at another nonce, or by anyone who is not the channel's depositor, is refused.

## Why a policy signer rather than a key in the hub

`AIMARKET_ESCROW_SUBMIT_STRATEGY=external` moves the key out of the hub process, and on its
own that buys very little: the hub posts `{to, data, chainId, gas, value}` and a naive signer
signs whatever it is handed. A compromised hub with the bearer token would then ask for
`USDC.transfer(attacker, everything)` and the key would sign it. So the value is entirely in
the refusals, and those are enumerated as rules R1–R26 in `escrow_signer/policy.py`,
`ledger.py` and `calldata.py`.

The residual risk that no signer can close, stated plainly: **a compromised hub can still
collect, without delivering service, everything buyers have already validly signed for, up to
the velocity caps.** Every field the contract checks is covered by the depositor's digest, so
a signature the depositor really produced is indistinguishable from the row the mirror wanted.
It shrinks with smaller caps and with buyers signing per invocation rather than in advance.

## Deploy

```
scp -r escrow-signer/ signer-host:/root/escrow-signer/
cp .env.example .env      # on the host, chmod 600, fill in the key and the token
docker compose up -d --build
curl -s localhost:9500/health     # {"ok":true,"ready":true,...}
```

Then, on the **hub** host:

```
cp deploy/escrow-signer-tunnel.service /etc/systemd/system/
systemctl enable --now escrow-signer-tunnel
# only the hub container may open the forward (the tunnel binds the Docker bridge)
install -m 755 deploy/signer-hub-only.sh /usr/local/sbin/
cp deploy/signer-hub-only.service deploy/signer-hub-only.timer /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now signer-hub-only.timer
curl -s localhost:9500/health     # the tunnel, not the service

cd /root/claudecode/aicom && ./scripts/deploy_hub_rebuild.sh --no-build \
  --set AIMARKET_ESCROW_SUBMIT_STRATEGY=external \
  --set AIMARKET_ESCROW_SIGNER_URL=http://127.0.0.1:9500/sign \
  --set AIMARKET_ESCROW_SIGNER_TOKEN="$(cat /root/.escrow-signer-token)" \
  --set AIMARKET_ESCROW_SUBMIT_CONFIRM=i-understand-this-moves-funds
```

`plan` first, always — it builds the real calldata and runs it through `eth_call` against
live state, so it answers "would this be accepted right now?" without a transaction existing:

```
docker exec modelmarket-hub python -m aimarket_hub.escrow_bridge.cli plan
docker exec modelmarket-hub python -m aimarket_hub.escrow_bridge.cli submit --yes
```

The fourth gate is deliberate: nothing broadcasts from the request path in any strategy, so
regular settlement is a timer on the hub host running `submit --yes`, not a background thread.

## Operating it

- `GET /health` — readiness, the address, and why it is refusing if it is. No ledger write.
- `GET /status` — the caps in force and the ledger's state.
- `GET /receipt/<receipt_id>` — the authoritative view of what this service broadcast. The
  hub's `confirm()` treats a returned hash as proof; this is where that can be checked
  against something that did not come from the same answer.
- It boots into a **refusing** state and stays there until the books verify, the chain agrees
  it is an authorized hub, the domain separator matches, and every unresolved row is
  classified from chain evidence. A stalled queue is better than an unmetered signature.

**The address is also the payee.** `settleChannel` pays `ch.hub`, which is this key, so
revenue accumulates here rather than in the treasury. With `SIGNER_SWEEP_TO` set the service
sweeps it itself: once per `SIGNER_SWEEP_INTERVAL_S` (default one day), when its own USDC
balance reaches `SIGNER_SWEEP_MIN_UNITS` (default 1 000 000 = 1.00 USDC), it signs one ERC-20
`transfer` of that whole balance to that address. It is the only token transfer this key ever
signs, no request can trigger it or name another recipient, and it takes its nonce from the same
ledger as the debits. **Never send from this key by hand:** the ledger hands out nonces and re-reads
the chain only at boot, so a manual transaction leaves the next debit one nonce behind until a
restart (it happened on 2026-10-06).

## Caps

All in integer USDC base units (6 dp). Every one is required — a missing, zero or negative
value refuses to start, and "no limit" must be spelled `unlimited` and is announced at every
boot. There is deliberately **no per-pass cap**: no pass id exists in the wire format, and any
"pass" inferred from idle gaps can be reset by pacing requests. Per-pass stays in the hub.

The count caps are not redundant with the dollar caps: receipt burning and nonce grinding cost
nothing in USDC and are bounded only by counts. `SIGNER_CAP_FEE_WEI_24H` is separate again,
because the dollar caps are denominated in the token while the drain vector is the key's ETH.

## Tests

```
python -m pytest escrow-signer/tests -q      # 95 tests
```

`tests/test_wire.py` imports the hub's own `ExternalSigner` and drives it against a real
socket — including the assertion that **no route ever answers 3xx**, because `urllib` follows
redirects with the `Authorization` header attached, which would turn a trailing slash into
token disclosure. `tests/test_policy.py` is the refusal table; every case asserts that nothing
was signed and nothing was broadcast, not merely that a status code came back.
