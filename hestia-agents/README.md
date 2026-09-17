# HESTIA agents

Three deterministic AIMarket capability providers, built to run as HESTIA
template tenants.

Each one is a pure function of its payload — no clock, no randomness, no
network, no filesystem. That is the product, not a limitation. HESTIA signs
every response with Ed25519 over the result, the capability id and the SHA-256
of the input; a signature over a value nobody else can reproduce proves
nothing. Determinism is what makes the receipt worth paying for.

| Agent | Capability | What it answers |
|---|---|---|
| `rules-decide` | `rules.decide@v1` | Which rule decided this, and why every earlier rule did not |
| `json-canonical` | `json.canonical@v1` | The one byte sequence this JSON must serialise to before signing |
| `commit-referee` | `commit.referee@v1` | Did the reveal match — and could the committer have opened it another way |

## Quick start

```bash
uv sync --extra dev --project .
uv run --project . pytest -q

# against a hearth you are running (see ../hestia)
export HESTIA_DEPLOY_TOKEN=...
uv run --project . python -m hestia_agents.cli deploy --hearth http://127.0.0.1:9480
uv run --project . python -m hestia_agents.cli verify --hearth http://127.0.0.1:9480
```

`verify` invokes each agent twice and compares both the result and the
signature. If a signature ever differs between two identical calls, the agent
has stopped being deterministic and its receipts are worthless — the check is
there to catch that the day it happens.

`deploy` never announces. Putting a row in the Hub catalogue is an explicit,
outward-facing act; pass `--announce` when you actually mean it.

## The agents

### `rules-decide` — decisions you can argue with

Send a versioned rule set and a set of facts. Get the decision, the rule that
fired, and a trace showing why each earlier rule did not.

```json
{"policy": {"id": "refund@2026-09",
            "rules": [{"id": "R1-window",
                       "when": [{"fact": "days_since_purchase", "op": "<=", "value": 14},
                                {"fact": "opened", "op": "==", "value": false}],
                       "then": {"decision": "approve", "reason": "unopened inside 14 days"}}],
            "default": {"decision": "deny", "reason": "outside the refund window"}},
 "facts": {"days_since_purchase": 31, "opened": true}}
```

Operators: `==` `!=` `<` `<=` `>` `>=` `in` `not_in` `matches` `exists`.
Numeric comparison goes through `Decimal(str(x))`, so `0.1 + 0.2` problems
never reach a money threshold. A missing fact fails its condition and says so
rather than raising. The response carries `policy_sha256` and `facts_sha256`,
so a receipt names exactly which policy version decided.

### `json-canonical` — the same bytes everywhere

RFC 8785 (JCS) canonicalisation plus SHA-256/384. Keys sort by UTF-16 code
unit, not code point — the two orders disagree above the BMP, which is where
naive implementations quietly diverge.

It **refuses** floats and integers beyond 2^53-1. JCS serialises numbers with
ECMAScript rules, so a float can canonicalise one way here and another way in a
JavaScript verifier, and a large integer cannot survive that verifier at all.
Emitting bytes that might not reproduce is worse than refusing. AWR receipts
are integers-only for the same reason.

### `commit-referee` — was the commitment actually binding

Checks a reveal against its commitment, and reports whether the scheme itself
binds.

`sha256(salt || value)` with a variable-length salt is ambiguous: `("abc","def")`
and `("ab","cdef")` produce the same commitment, so a committer can still pick
which one to reveal after seeing the outcome. Layout `lenprefix`
(`sha256(len(salt) || salt || value)`) removes that. The referee verifies the
hash and flags the layout — see `test_referee_flags_a_layout_that_opens_two_ways`,
which demonstrates two different reveals verifying against one commitment.

Layouts: `lenprefix` (recommended), `separator`, `concat`, `value`.
Algorithms: `sha256`, `sha384`, `sha512`.

## Limits worth knowing before writing a fourth

- A template handler is capped at **32 000 characters**, and the request body at
  **256 KiB** by default. Reference data — holiday calendars, price books,
  licence matrices — will not fit in the source and has to arrive in the
  payload, or the agent becomes a pinned image instead.
- Handlers are admitted by AST, which is **admission control, not a sandbox**:
  an admitted handler still executes as a same-host subprocess. It is bounded —
  a per-call deadline (10s), an address-space cap (512 MiB), a container mem/pids
  limit and a response cap — but that is not cgroup isolation. For enforced
  CPU/memory isolation run `HESTIA_RUNTIME=docker`.
- Priced handlers **are** charged now: see "Getting paid" below.

## Getting paid — live

Payments are wired and on at the reference host. `price_per_call_usd` is the
price; a priced agent charges it non-custodially.

- A priced call to `POST /t/{slug}/invoke` (or the routed `/ai-market/v2/invoke`)
  returns **402** with x402-shaped terms naming the agent owner's own payout
  address, the amount in USDC base units, and the chain.
- The buyer sends USDC **directly to that address** on Base, then retries with
  header `X-Payment: <tx hash>`. HESTIA verifies the on-chain transfer
  (`hestia.payments`), records the transaction so one payment buys one call, and
  serves the result. **The host holds no key and takes no cut** — it reads the
  chain, it never touches the money.
- If the tenant is unreachable after payment is claimed, the claim is released
  so the same transaction can be retried.
- `payout_address` is set per agent at deploy (see `hestia_agents/manifests.py`);
  `owner_pubkey` stays the Ed25519 signing identity, which is a different thing.

Ask an agent what it costs with `python -m hestia_agents.cli quote`, and pay-and-
call with `python -m hestia_agents.cli call <slug> --tx 0x…`.

## Layout

```
agents/<slug>/handler.py    the source the hearth executes
agents/<slug>/deploy.json   generated deploy body — do not hand-edit
hestia_agents/manifests.py  capability metadata and body generation
hestia_agents/cli.py        build / deploy / verify
tests/                      admission, behaviour, determinism
```

`deploy.json` embeds the handler source, so the two drift the moment anyone
edits one by hand. Regenerate with `python -m hestia_agents.cli build`; a test
asserts they match.

## Licence

MIT. Part of the AICOM agent economy.
