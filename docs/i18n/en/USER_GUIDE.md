# User guide

## 1. Buy access

Choose Personal, Team or Market on `/billing`. The checkout returns the exact
USDC amount, recipient, token address, chain and expiry. Send the exact amount
on Base, wait for the required confirmations and paste the transaction hash.

## 2. Store the key safely

The `ask_...` key is returned once. Store it in a password manager or a secret
manager. Use `POST /v1/keys/rotate` before sharing a replacement and
`POST /v1/keys/revoke` when access must stop.

## 3. Create an actor identity

Send the active paid key as `X-SaaS-Key`; it is separate from the actor proof.

The Hub expects `X-Actor-ID`, `X-Actor-Public-Key` and
`X-Actor-Signature`. The signature covers the actor ID; the private key stays
in your client or agent runtime.

## 4. Write and retrieve memory

Send a JSON body with `title`, `content`, `tags`, `visibility` and optional
`source_refs` to `/memory/api/memories`. Search with `/memory/api/search`.
Personal private reads require the same actor identity that owns the memory.

## 5. Use Team Memory OS

Create a team through `/teams/api/teams`, add members through
`/teams/api/teams/{team_id}/members`, and include `team_id` on every team
write/search. The gateway checks membership; the Hub checks the short-lived
team assertion and actor signature.

## 6. Troubleshooting

`401` means the SaaS key or actor proof is invalid. `403` means the product or
team scope is wrong. `402` means a paid Memory Unit needs settlement. `429`
means wait for the rate-limit window. Never send a private key to the API.

## 7. Trial

Start at `/v1/trials`: Personal lasts 7 days, Team 14 days, and Expert Market
1 day. The Gateway issues a one-time `ask_...` key without payment and binds
the entitlement to a verified actor. It expires automatically; continue with
the exact USDC-on-Base payment flow. See [TRIAL.md](TRIAL.md).
