# HISTOR's log is witnessed (staging witness network) — 2026-11-04

Rasmus Dahlberg (witness-network.org) added the log to the staging list on 2026-11-04 in answer to the 2026-10-30
request: https://staging.witness-network.org/log-list-10qps-4klogs.1 carries

    vkey histor.modelmarket.dev/log+ad3ca066+AfXpkWqXVW93sChXnhKsNzvGLTFAAredl1jLlEjbr4wU
    qpd 144

## Switched on (admin-vps, about 10:25Z)

The push timer (`histor-witness-push.timer`, every 10 minutes, installed 2026-10-30) does nothing until
`/etc/histor/witnesses.json` exists (`histor/deploy/witness_push.sh`). The first run with the whole staging template
(`histor/deploy/witnesses.staging.json`, four witnesses) got cosignatures from three and `404: unknown log` from
witness.gdbsecurity.com, whose about page says it re-reads the list every 24 h. Pushing to a witness that does not know
the log yet is what the script avoids (it is noise for that operator, and the unit fails), so `/etc/histor/witnesses.json`
is the template without GDB for now:

| Witness | Operator | First cosignature |
|---|---|---|
| witness.stagemole.eu | Mullvad VPN AB | size 1597824 |
| markovianprotocol.com/witness | Markovian Protocol | size 1597824 |
| staging.witness.transparency.goog/ring-any-bells | TrustFabric | size 1597824 |
| witness.gdbsecurity.com | GDB Security | not yet (unknown log; list refresh 24 h) |

The second run cosigned size 1597825, so the witnesses also checked the consistency proof from the size they had
co-signed. The unit finished without error.

**To add GDB** once its list refresh has picked the log up (after 2026-11-05 ~10:30Z):
`cp /etc/histor/witnesses.staging.json /etc/histor/witnesses.json`, then `systemctl start histor-witness-push.service`
and read the journal; if GDB still answers `unknown log`, put the three-witness file back.

## Verified independently

`verify_checkpoint.py` (Python `cryptography` only, from c2sp.org/signed-note and c2sp.org/tlog-cosignature: key hash
SHA-256(name, newline, key type, key)[:4]; cosignature/v1 message `cosignature/v1\ntime <t>\n` + note) checks the
public https://histor.modelmarket.dev/checkpoint: the log's Ed25519 signature and the three witness cosignatures all
verify (`checkpoint-1597825.txt`).

## What would make it stronger

GDB's about page: a log found through the list is polled on its own schedule only if it serves its checkpoint and
tiles at `https://<origin>/` (here https://histor.modelmarket.dev/log/). HISTOR serves the checkpoint at the site root
and RFC 9162 proofs through its API, not c2sp.org/tlog-tiles, so witnesses see only what the log pushes them. Serving
tlog-tiles under /log/ would let them poll the log independently.
