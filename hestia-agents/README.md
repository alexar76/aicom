# HESTIA agents

Deterministic AIMarket capability providers, built to run as HESTIA template
tenants and sold under the operator's name (payouts to the treasury).

**Catalogue of all eleven agents, in five languages:** [English](docs/AGENTS.md) ·
[Русский](docs/AGENTS.ru.md) · [Español](docs/AGENTS.es.md) · [Français](docs/AGENTS.fr.md) ·
[中文](docs/AGENTS.zh.md) — what each answers, how to call it, an example request.

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
| `merkle-proof` | `merkle.proof@v1` | Is this entry in that log / that airdrop — and did the log only grow |
| `x402-check` | `x402.authorization.check@v1` | Who signed this x402 payment, for what — and will USDC accept it |
| `mcp-diff` | `mcp.tools.diff@v1` | What changed in an MCP server you approved — and does it look like a rug pull |
| `money-compute` | `money.compute@v1` | What this invoice, split or conversion comes to — to the last minor unit |
| `signature-verify` | `signature.verify@v1` | Did this key sign this receipt, credential or answer — byte for byte |
| `id-check` | `id.check@v1` | Is this IBAN, ISBN, GTIN, ISIN, LEI or wallet address real — or a typo |
| `confusables` | `text.confusables@v1` | Does this name pretend to be another one |
| `stats-test` | `stats.test@v1` | Did B really beat A — and how many visitors would it take to know |

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

### `merkle-proof` — proofs you can check without trusting the issuer

Builds roots and inclusion proofs, and checks one you were handed by recomputing the
root — never by trusting a `valid` flag that came with it. Two families:

- `rfc6962` (default): Certificate Transparency / RFC 9162, as HISTOR's log uses it.
  `leaf_format` `hex` (default), `utf8`, or `json` (the leaf is the RFC 8785 form of the
  value — a HISTOR label as published). Ops: `root`, `prove`, `verify`, `consistency`,
  `verify_consistency` — the last two answer "was the log only appended to?".
- `openzeppelin`: Solidity's `MerkleProof.verify` (sorted-pair keccak256). Leaves are
  bytes32 hashes, or `types` + `values` hashed as `StandardMerkleTree` does
  (`keccak256(keccak256(abi.encode(...)))`, mixed-case addresses checked against
  EIP-55). `layout` `standard` (@openzeppelin/merkle-tree) or `layers` (pairs left to
  right, an odd node promoted — merkletreejs, the ACEX distributor). At most 1 024 leaves:
  keccak256 is pure Python here.

```json
{"op": "verify", "leaf_format": "utf8", "leaf": "delta", "index": 3, "tree_size": 5,
 "proof": ["f931…", "fb33…", "4a3c…"], "root": "27fb…"}
```

Tested against the Certificate Transparency test-vector roots, the root in
@openzeppelin/merkle-tree's README, eth-abi leaf hashes, and HISTOR's and the ACEX
distributor's own trees over every index of 1–40 leaves.

Through a hub, the hub's safety gate scans the input first: a standalone 16-digit
Luhn-valid string reads as a card number and is refused there. Hash leaves never look
like that; called directly on the hearth, nothing is scanned.

### `x402-check` — will this payment go through, before anyone submits it

x402's `exact` scheme on EVM pays with USDC's EIP-3009 `transferWithAuthorization`. Send the
X-PAYMENT header (`x_payment`, base64), the decoded `payment`, or `authorization` +
`signature` (or `v`, `r`, `s`) + `network` (`base`, `base-sepolia`, … or `eip155:<id>`), and
optionally the seller's `requirements` (the 402's `accepts` entry) and `now`.

It recomputes the EIP-712 digest, recovers the signer (secp256k1, written out here: the
hearth has no crypto library) and reports each check: `v` (USDC takes only 27/28), `low_s`
(USDC reverts on the upper half), `signer`, `domain`, `window`, and against the
requirements `pay_to`, `amount`, `asset`, `network`, `nonce_binding`. The domains of USDC on
Ethereum, Base, Base Sepolia, Arbitrum, OP, Polygon and Avalanche were read from the
contracts; Base Sepolia's `name` is `USDC`, every mainnet's is `USD Coin`, and signing with
the other one is the commonest reason an x402 payment reverts. Whether the nonce is unused
and the balance covers it needs the chain, so it is listed under `not_checked`.

Tested against a payment that settled on Base (tx `0xd8a41fb8…`), the seven contracts' own
`DOMAIN_SEPARATOR()`, and eth-account signatures.

### `mcp-diff` — what changed in a server you already approved

Send two `tools/list` results of one MCP server as `old` and `new` (a list, `{tools}` or the
JSON-RPC `{result: {tools}}`). The answer lists tools added and removed, a word diff of every
changed description, the JSON paths of the schemas that moved and the annotation changes —
then raises signals on what the change ADDED, never on what a description already said:

| Signal | Severity | Example |
|---|---|---|
| `instruction_tag`, `override`, `conceal_from_user`, `preempt_other_tools` | high | `<IMPORTANT>`, "ignore the other tools", "do not tell the user", "before using any other tool" |
| `credential_path`, `covert_action`, `html_comment`, `hidden_characters` | high | `~/.ssh`, `mcp.json`, "silently forward", `<!--`, zero-width / bidi / tag characters |
| `duplicate_name`, `non_ascii_name` | high | two tools named alike, a Cyrillic `а` in a tool name |
| `new_address`, `send_elsewhere`, `references_other_tools` | medium | a host, e-mail, IP or wallet the old set never named; a tool rewriting another tool |
| `permission_widened`, `new_sink_parameter` | medium | `readOnlyHint: true` dropped; a new `webhookUrl` / `command` / `path` parameter |
| `credential_request`, `embedded_blob`, `pushed_out_of_view` | medium | "your API key", a long base64 run, 40 blank characters before the real text |

Verdict: `unchanged`, `changed` (no signal), `review` (medium) or `suspicious` (high). The
phrases are English; addresses, hidden characters, names and schema changes read the same in
every language. HISTOR's continuity log flags a changed tool set; this says what changed.

Through a hub, the hub's own safety gate reads the input first and refuses some hostile text
outright (`ignore all previous instructions`, `<system>`, e-mail addresses as PII). To diff a
server whose descriptions carry those, call the hearth directly.

### `money-compute` — arithmetic a model should not do in its head

Decimal throughout (never float); every rounding names its mode and where it happened.

- `invoice`: `lines` of `quantity` x `unit_price`, an optional line `discount`
  (`{percent}` or `{amount}`) and `tax_rate` (percent; `tax_rate` at the top is the default).
  `tax_inclusive` prices, `rounding_level` `line` (round each line) or `rate` (round each
  tax-rate total — the two differ by a cent often enough to matter), and a tax breakdown.
- `split`: `amount` by `shares` (weights, percents, basis points, or `[{name, weight}]`).
  Always sums to the amount exactly: the leftover minor units go to the largest fractional
  remainders, ties to the earlier share (`method` `first` / `last` to choose otherwise).
- `convert`: `amount` x `rate` (you supply the rate; there are no live prices here), rounded
  to the target currency, with the rounding error stated.

Minor units: ISO 4217 (`JPY` 0, `KWD` 3, most 2), `USDC`/`USDT` 6, `BTC` 8, `ETH` 18, or
`decimals`. Amounts are decimal strings (`"19.99"`); thousands separators are refused rather
than guessed. Through a hub, an amount with exactly nine integer digits (100 000 000–
999 999 999) reads as an SSN to the hub's PII gate; call the hearth directly for those.

### `signature-verify` — receipts and credentials, checked by anyone

Ed25519 (RFC 8032, written out: the hearth has no crypto library; cofactorless like
OpenSSL, refusing non-canonical points, `S >= L` and small-order keys). `format` is detected
from the document or given:

| `format` | Signed bytes |
|---|---|
| `raw` | `message` (`utf8` / `hex` / `base64`) |
| `jcs` | RFC 8785 form of `document` minus `exclude` keys (integer numbers only) |
| `eddsa-jcs-2022` | W3C Data Integrity: SHA-256(JCS(proof config)) ‖ SHA-256(JCS(document)); proof sets too |
| `histor` | JCS of a HISTOR document without its `signature` (tree heads, labels) |
| `hestia` | a hearth agent's answer, bound to the `input`, `capability_id`, `product_id` you sent |
| `hub-receipt` | an AIMarket hub receipt, v1 or v2 canonical (and the hub's 0.0 / 0 twin) |
| `hub-object` | a whole object a hub or hearth signs (its `.well-known`, compute receipts) |

`public_key` (hex, base64, `did:key:` or `z6Mk…`) pins WHO signed; a document naming another
key is then invalid. Without it the document's own key is used and the answer says the key
was self-asserted: integrity, not identity. For credentials the proof's key must also be the
issuer's, and `proofPurpose` must be `assertionMethod` (or `proof_purpose`).

A defect in the signed material is an answer (`valid: false` and the reason), not an error.
Tested against RFC 8032, `cryptography`, every AWR/2 conformance vector (all valid documents
verify; every invalid one whose defect is in the proof, key or canonical bytes is refused —
the rest break AWR's own rules and carry genuine signatures), a live HISTOR tree head, and
the hub's and the hearth's own signers.

### `id-check` — a typo caught before money or goods move

`id` (one) or `ids` (up to 1 000, strings or `{id, type}`); `type` is detected when not
given. Identifiers of accounts, products, publications, securities, companies and wallets —
never of people: no payment cards (the holder's secret, and a hub's PII gate refuses them
anyway), no national IDs.

| `type` | Check |
|---|---|
| `iban` | the country's length (89 countries, as Wikipedia's registry table lists them) and mod 97; compact form only (a grouped "DE89 3704 …" reads as a card number to a hub's PII gate) |
| `bic` | ISO 9362 shape only — a BIC has no check digit, and the answer says so |
| `isbn` | ISBN-10 (mod 11, `X`) with its ISBN-13 form, ISBN-13 |
| `gtin` | EAN-8, UPC-A, EAN-13, GTIN-14 (mod 10, weights 3/1) |
| `issn` | mod 11, `X` (an 8-digit ISSN without its hyphen reads as EAN-8: send `type`) |
| `isin` | Luhn over the letter expansion — which misses some letter swaps (`US…`/`ES…`) |
| `lei` | ISO 17442 mod 97 |
| `evm` | mixed case must carry a correct EIP-55 checksum; a wrong one is never "corrected" |
| `bitcoin` | Base58Check (P2PKH, P2SH, testnet) and Bech32 / Bech32m segwit, with the scriptPubKey |

Tested on published examples, all BIP 350 vectors (copied from bitcoin/bips), and every
single-character substitution of IBAN, LEI, ISBN and GTIN examples. Through a hub, an EAN-13
that starts with 4 and also passes the card checksum reads as a card number to the PII gate.

### `confusables` — a name that pretends to be another

`text` or `texts` (up to 500), optionally `against` (the names you protect) and
`kind: domain` (labels split, `xn--` punycode decoded first). Each name gets a `risk`
(`none` / `medium` / `high`), its UTS #39 skeleton, its scripts, and the issues found:

- `mixed_script` (high) — Latin with Cyrillic or Greek in one name; the Japanese, Chinese and
  Korean mixes UTS #39 allows (Latin + Han + kana / Bopomofo / Hangul) are not flagged.
- `confusable_with` (high) — same skeleton as a protected name, but not that name
  (`pаypal`, `rnodelmarket`, `modeImarket`, `ｍodelmarket`, `model​market`).
- `invisible`, `bidi_control` (high) — zero-width, tag, variation characters; bidi controls
  that reorder what is shown (Trojan Source).
- `whole_script`, `compatibility`, `confusable_ignoring_accents`, `punycode` (medium).

The prototype table is a curated subset of Unicode's confusables (Cyrillic, Greek,
Armenian and Cherokee letters that pass for Latin; rn/m, vv/w, cl/d, I/l/1, O/0) — the full
`confusables.txt` would not fit a template handler. Punycode is RFC 3492, checked against
Python's codec. Honest single-script names in any language pass.

### `stats-test` — "B beat A", computed rather than guessed

| `op` | Answers |
|---|---|
| `proportions` | two conversion rates: pooled z test, the difference's CI, Wilson CIs per arm; Fisher's exact test takes over when an expected count is below 5 |
| `means` | Welch's t test from `{mean, sd, n}` or `{values}`, with Cohen's d |
| `chi_square` | an r x c `table` of counts: chi-square, expected counts, Cramér's V, a small-count warning |
| `sample_size` | per group, for a rate (`baseline` + `mde` or `relative_mde`) or a mean (`sd` + `mde`) |
| `proportion_ci` | Wilson and Clopper-Pearson (exact) intervals for one rate |
| `describe` | n, mean, median, sd, quartiles, Tukey outliers |

`alternative` (`two-sided`, `greater` = b above a, `less`) and `alpha` apply throughout, and
every answer lists the assumptions it rests on (independent units, no peeking). The t,
chi-square and beta distributions are computed here — regularized incomplete beta and gamma
functions by continued fractions — and tested against printed critical values, closed forms,
Fisher's tea-tasting table (34/70) and Evan Miller's A/B sample size (8 158 per group for
5% → 6%).

## Limits worth knowing before writing another

- A template handler is capped at **32 000 characters**, and the request body at
  **256 KiB** by default. Reference data — holiday calendars, price books,
  licence matrices — will not fit in the source and has to arrive in the
  payload, or the agent becomes a pinned image instead.
- On the reference hearth (`HESTIA_RUNTIME=wasm`) a handler runs in the hearth's
  WebAssembly sandbox: a fresh CPython-for-WASI instance per call, 256 MiB, 10 s,
  4 MiB of output, no host files, network, processes or secrets. Keep handlers
  pure Python (no `zlib`, sockets or threads in the WASI build) and expect a pure-
  Python hash or curve to run about three times slower than native — the Merkle
  agent caps typed trees at 1 024 leaves for that reason. Under the stub runtime
  the AST allow-list applies instead (admission control, not a sandbox).
- Priced handlers **are** charged now: see "Getting paid" below.

## Getting paid

Payments are wired into the hearth; whether a tenant charges is the operator's
switch (`HESTIA_PAYMENTS_ENABLED`, off unless it is set). `price_per_call_usd` is
the price, and a priced agent charges it non-custodially.

- A priced call to `POST /t/{slug}/invoke` (or the routed `/ai-market/v2/invoke`)
  returns **402** with x402-shaped terms naming the agent owner's own payout
  address, the amount in USDC base units, and the chain.
- The 402 also carries a fresh `nonce` and a `payment_secret` (`"binding": "eip3009"`),
  with nonce = sha256(secret). The buyer pays with an EIP-3009
  `transferWithAuthorization` signed over that nonce, then retries with `X-Payment: <tx hash>` and `X-Payment-Secret: <secret>`.
  HESTIA reads the transfer and its `AuthorizationUsed` log on chain
  (`hestia.payments`), records it so one payment buys one call, and serves the
  result. **The host holds no key and takes no cut** — it reads the chain, it
  never touches the money.
- Why the secret: once the payment is mined, its transaction hash and its nonce
  are public. Redeeming on those alone let anyone watching the chain present
  them first and take the call the buyer paid for, and the buyer was then refused
  as "already spent". The secret never goes on chain; the nonce is only its hash.
  Keep it to yourself until you call.
- Redeem promptly. The hearth stops redeeming a nonce when its invoice expires
  (`expires_at`, 900 s after the 402 unless the operator says otherwise), so `pay`
  never builds a deadline past that and prints the time to redeem by. And a secret
  that sits in a file or a shell history is only worth taking until the call is
  served: after that the payment is spent, and the secret redeems nothing.
- A 402 that binds nothing (`"binding": "none"`), or binds a nonce but hands over no
  `payment_secret` (a hearth from before commit-reveal), is refused by `quote`, `pay`
  and `call` with "Do not pay it": whoever presented such a payment first would take
  the call, and the hearth itself no longer accepts one.
- If the tenant is unreachable after payment is claimed, the claim is released
  so the same transaction can be retried.
- `payout_address` is set per agent at deploy (see `hestia_agents/manifests.py`);
  `owner_pubkey` stays the Ed25519 signing identity, which is a different thing.

Nothing here signs or holds a key. The flow is quote, pay in two steps, call:

```bash
hestia-agents quote --hearth $H --only json-canonical
# step 1: typed data to sign, plus the nonce, deadline, redeem-by time and
# payment secret it used
hestia-agents pay json-canonical --hearth $H --from 0xYOURADDRESS
# step 2: give back what step 1 printed with the signature; prints calldata
hestia-agents pay json-canonical --hearth $H --from 0xYOURADDRESS \
    --nonce 0x… --valid-before 17… --amount 1000 --pay-to 0x… --signature 0x…
# send that calldata to the token contract from the signing address, then,
# before the redeem-by time
hestia-agents call json-canonical --hearth $H --tx 0x… --secret 0x…
```

`quote` shows the nonce and secret of its own 402, for a buyer who signs with
their own tools. `pay` asks for a 402 of its own, and every 402 mints a new
pair, so a payment `pay` builds is redeemed with the secret `pay` prints, never
with `quote`'s; `quote` says so.

Step 2 takes the nonce, deadline, amount and payee back rather than asking
again: every 402 mints a new nonce and the signature covers all four, so
calldata rebuilt from a fresh 402 or a fresh clock is a transaction the token
contract reverts (step 2 used to do exactly that). The fresh 402 must still ask
that amount of that payee; after a redeploy between the steps it may not, and
what step 1 signed would no longer buy the call, so step 2 refuses and says to
run step 1 again. A hearth from before the secret sends no `payment_secret`;
`quote` and `pay` say so, and `call --nonce` redeems there.

Only a 200 is free and only a 402 that states its terms is a price: `quote` exits
1 on anything else (a 404 or 500 used to read as "free right now"), and on a
`payment_secret` that does not open its nonce or is guessable. `pay` refuses in
one line, in either step, a `--from` that is not an address, a negative
deadline, and a 402 whose payee, amount, chain id or token contract is missing
or malformed. Step 1 also refuses, before printing anything to sign, a
`--valid-before` later than the nonce's expiry, a nonce that has already
expired, a 402 whose nonce is malformed (or, on a hearth that binds, whose
expiry is), and a `payment_secret` that does not open its nonce or is guessable. Step 2 refuses, before printing any
calldata, a missing or malformed `--nonce`, `--amount` or `--pay-to`, a fresh
402 that asks another amount or payee, and a signature whose r/s are not 32
bytes of hex or whose v is not 27/28 (0/1).

A 402 answered to `call --tx` (or `compute --tx`) prints the hearth's refusal
and nothing else: the payment has been made, and the terms or a build-it line
printed after it read as an invitation to pay a second time for one call.

The secret need not go on a command line, where shell history and `ps` keep it:
`--secret @file` reads it from a file, and `call --tx`, `compute --tx` and
`pay-compute --signature` read `HESTIA_PAYMENT_SECRET` when no `--secret` is
given (a `--secret` that is given wins). Without `--tx` the environment is not
read, so a secret left there does not turn a free call into a refused one.
Commands printed for the next step name the secret the way it was given — a
file as the file, the environment not at all.

## Compute and cross-hearth checks

A hearth with compute on (`../hestia/docs/COMPUTE.md`) sells these same pure
functions as `hestia.compute.run@v1` (one measured replica) and
`hestia.compute.verify@v1` (two replicas, signed only if they agree). This
package is also the buyer for that:

```bash
pip install 'aimarket-hestia-agents[compute]'
export HESTIA_COMPUTE_API_KEY=...        # when the hearth sells to you by key
hestia-agents compute json-canonical --hearth https://a.example \
    --input '{"document": {"b": 1}}' --replicated
hestia-agents cross-verify json-canonical --hearth https://a.example \
    --hearth https://b.example --input @doc.json --verdict-out verdict.json
```

A hearth may also sell compute directly, to a buyer with no key: it names a
payout address used for compute and nothing else. That door mints no nonce —
on the production rail the hub is the till, and a second nonce would be a
second till one authorization cannot satisfy — so the buyer picks one, as
sha256 of a secret only they hold (`"binding": "secret"`,
`"nonce_rule": "sha256(secret)"`). A plain transfer, or a secret that does not
open the nonce on chain, is refused at that door, for the same reason as above:
the transaction and its nonce are public once mined. A hub's keyed forward is
the hub's business: it names its own invoice's nonce and needs nothing from a
direct buyer.

```bash
# step 1: makes up the secret (or pass --secret 0x… or --secret @file), prints
# typed data to sign
hestia-agents pay-compute json-canonical --hearth https://a.example --from 0xYOURADDRESS
# step 2: the same --secret and --valid-before, with the signature; prints calldata
hestia-agents pay-compute json-canonical --hearth https://a.example --from 0xYOURADDRESS \
    --secret 0x… --valid-before 17… --signature 0x…
# send it, then present the transaction and the secret, within the door's
# max_age_s of it being mined
hestia-agents compute json-canonical --hearth https://a.example --input @doc.json \
    --tx 0x… --secret 0x…
```

Pass `--replicated` to both `pay-compute` and `compute` to buy the replicated SKU:
the price is per SKU, and what was signed is that price. `pay-compute` refuses, in
one line and before anything is signed, a hearth that does not bind by secret.

A secret you choose is held to the hearth's own rule first. The door refuses one
with fewer than 16 distinct bytes as guessable (32 random bytes hold about 30; a
pattern such as `0x00…00` is one anyone could precompute and open), and it would
say so only after you had paid under it. So `pay-compute --secret`,
`compute --secret`, `compute.call(payment_secret=…)` and `call --secret` refuse
such a secret in one line, before anything is asked, signed or sent; the ones
this tool makes up are drawn again in the (vanishingly rare) case they would be
refused. Step 1 of `pay-compute` never reads `HESTIA_PAYMENT_SECRET`: a secret
left in the environment would sign every new payment over one nonce, which the
token accepts only once.

Two replicas on one hearth are one operator checking itself (the receipt says
`same_operator: true`). `cross-verify` is the step past that: the same pinned
`function_sha256` on two hearths with different keys, each receipt checked
against the key its hearth publishes, input and output digests recomputed here,
outputs compared. It refuses before paying anyone when both hearths share a key,
list different bytes under the slug, or either lists no `function_sha256` at all
(two missing digests used to compare equal, and both hearths were paid unpinned). With the `awr` package installed,
`--verdict-out` writes an AWR `VerificationVerdict` over the first receipt.

## Layout

```
agents/<slug>/handler.py    the source the hearth executes
agents/<slug>/deploy.json   generated deploy body — do not hand-edit
hestia_agents/manifests.py  capability metadata and body generation
hestia_agents/cli.py        build / deploy / verify / quote / pay / call /
                            compute / pay-compute / cross-verify
hestia_agents/compute.py    compute buyer: receipt checks, cross-hearth comparison
hestia_agents/x402.py       402 -> typed data -> calldata; the payment secret rule
tests/                      admission, behaviour, determinism
```

`deploy.json` embeds the handler source, so the two drift the moment anyone
edits one by hand. Regenerate with `python -m hestia_agents.cli build`; a test
asserts they match.

## Licence

MIT. Part of the AICOM agent economy.
