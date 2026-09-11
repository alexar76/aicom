# Field manual

## Pay once. Keep the key.

Choose Personal, Team or Market on `/billing`. Checkout locks the exact USDC
amount, recipient, token, chain and expiry. Send that amount on Base, wait for
confirmations, paste the transaction hash.

The paid `ask_...` key can be recovered with the checkout secret for 48 hours;
after that only its hash remains. Store it in a password manager. Status keeps
reconciling even if the browser closes. Rotate with `POST /v1/keys/rotate`,
revoke with `POST /v1/keys/revoke`, inspect with `GET /v1/keys/me`.

## Prove who acts. Write what lasts.

Pass the SaaS key as `X-SaaS-Key` — it is not the actor proof.

Protected calls need `X-Actor-ID`, `X-Actor-Public-Key` and `X-Actor-Signature`.
The private key stays in the browser or agent runtime. Write memory through
`/memory/api/memories`; search through `/memory/api/search`. Private personal
reads require the same actor that owns the memory.

## Run a team without shared secrets.

Create a team at `/teams/api/teams`, add members at
`/teams/api/teams/{team_id}/members`, and send `team_id` on every team call.
The Gateway checks membership; the Hub checks a short-lived team assertion and
the actor signature.

`401` — bad key or proof. `403` — wrong scope. `402` — settlement required.
`429` — rate limit. Never send a private key to the API.

## Start free. Convert cleanly.

Claim a trial at `/v1/trials`: Personal 7 days, Team 14 days, Expert Market
1 day. The Gateway issues an actor-bound `ask_...` without payment; the same
signed actor can recover it while active. It expires on its own — continue with
exact USDC on Base. See [TRIAL.md](TRIAL.md).

## KOVA stays separate. Checkout stays exact.

Agents discover KOVA through Hub federation. Attested checkout uses a protected
service-to-service route so capability spend cannot recursively bill itself.
Both paths, receipts and boundaries live in
[KOVA_CAPABILITIES.md](KOVA_CAPABILITIES.md).
