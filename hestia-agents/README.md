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
  an admitted handler still executes in the tenant process. The stub runtime
  cannot cap CPU or memory. For enforced limits run `HESTIA_RUNTIME=docker`.
- Handlers are billed at `price_per_call_usd` in the manifest, but **nothing in
  HESTIA charges it**: the invoke edge proxies anonymously and no payout path
  exists yet. See "Getting paid" below.

## Getting paid — not wired yet

`price_per_call_usd` is metadata. As of 2026-09-17 there is no payment path:

- `POST /t/{slug}/invoke` proxies with **no token and no payment check** — an
  anonymous call returns 200 and costs the caller nothing.
- `owner_pubkey` is stored in the ledger and never read again. It is an Ed25519
  key, not a payout address, so even a wired-up escrow would not know where to
  send USDC.
- `announce` federates **the hearth**, and the hearth's `/ai-market/v2/manifest`
  advertises only HESTIA's own four host capabilities. A tenant's capability is
  not in it, so announcing does not put these agents in the Hub catalogue.

Closing that needs three things, in order: tenant capabilities in the hearth
manifest, a payout address on the tenant record, and a paid invoke path on the
edge that settles through the Hub escrow.

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
