# SYMMARTYS deployment and hostname

SYMMARTYS 0.5.0 is deployed with its existing keys and data preserved. Since
2026-10-29, the public landing and direct API are served at
https://symmartys.modelmarket.dev/ over HTTPS. The federation keeps its canonical
provider URL `https://modelmarket.dev/providers/symmartys`; both addresses serve the
same provider. Source and registry publication remain pending.

The procedures below cover future upgrades. They do not independently authorize
a deployment, DNS or certificate changes, registry publication, or a GitHub write.

`scripts/deploy_symmartys.sh` retains `/opt/emporion` when that directory exists;
otherwise it selects `/opt/symmartys`. `--dest /absolute/path` overrides this choice.
The new source goes into `DEST/src/symmartys`; the old source and installation
`.env` remain available for recovery. Docker data is never renamed or removed.

## Prepare an upgrade

Before the maintenance window, record the existing provider's public signing key
from `/.well-known/ai-market.json` (`signer_public_key`), or the signed manifest's
`signature.public_key`. Record the mounted Docker data-volume name using
`docker inspect emporion` locally; do not paste its complete configuration or
environment into a chat or public log.

In the existing installation `.env`, set:

```dotenv
SYMMARTYS_VOLUME_NAME=THE_EXISTING_DATA_VOLUME
SYMMARTYS_EXPECTED_SIGNER_PUBLIC_KEY=THE_EXISTING_BASE64_PUBLIC_KEY
```

Keep the existing secret values, `ORACLE_TRUSTED_HUBS`, database settings and
operator token. The script copies legacy `EMPORION_*` key names to `SYMMARTYS_*`
without evaluating their values. Explicit new keys take precedence. It retains
the original file as `.env.before-symmartys`, mode600, before an actual change.
For multiline quoted legacy settings, migrate the names manually: the helper
refuses to guess. It prints key names, never credentials or rendered Compose.

A known legacy product URL becomes `https://modelmarket.dev/providers/symmartys`.
The old URL and existing `ORACLE_HUB_AUDIENCES` entries remain accepted signing
audiences. Trusted-hub public-key pins are retained. Review customized public URLs
and the hub's provider URL/capability configuration together before cutover.

The script refuses a running `emporion` container or another container publishing
port9351. It never stops or deletes the legacy container. Stopping that runtime is
an explicit operator maintenance action after backups and a recovery plan exist;
it is not performed by this script. Preserve its image, source, environment
and volume so the operator can restore the old runtime if necessary.

Once new source is staged and the old runtime has been deliberately stopped:

```bash
sudo bash /opt/emporion/deploy/deploy_symmartys.sh --dest /opt/emporion --check
```

`--check` validates the prospective environment and existing volume read-only.
It creates no containers, volumes, files or nginx changes. An eventual approved
deployment omits `--check`; laptop staging uses `--remote HOST --dest /opt/emporion`.
The new process must report `service=symmartys`, new capability IDs and the recorded
signing key. A failed candidate restores the previous SYMMARTYS image when one
exists, or stops only the new candidate. Restoring the retained legacy runtime is
an operator action; no automatic legacy stop/start/delete is hidden in the script.

## Dedicated hostname

The vhost is a template because the landing may still live under `/opt/emporion`.
Render it for the actual destination, review it, then install only during an
approved DNS/TLS/nginx change:

```bash
bash scripts/deploy_symmartys.sh --dest /opt/emporion \
  --render-vhost /tmp/symmartys.modelmarket.dev.conf
```

Never install the unrendered template. A certificate for the new hostname must
exist before enabling its HTTPS block. The ordinary deploy script manages the
apex `/providers/symmartys/` snippet and validates nginx before reloading it.

The installed dedicated vhost is
`/etc/nginx/sites-available/symmartys.modelmarket.dev`, rendered for
`/opt/emporion`. Its Let's Encrypt certificate is managed by the existing
`certbot.timer`. Renewal uses the HTTP webroot `/var/www/certbot` and a persisted
`systemctl reload nginx` deploy hook, so a renewed certificate becomes active
without restarting the provider. Keep the ACME HTTP location available.

Check the timer and exercise renewal without replacing the live certificate:

```bash
systemctl status certbot.timer
certbot renew --cert-name symmartys.modelmarket.dev --dry-run \
  --run-deploy-hooks --non-interactive
```

## Deliberate fresh installation

Use a new destination, an explicit new `SYMMARTYS_VOLUME_NAME`, and `--fresh-volume`.
Only this flag permits creation of a missing volume and omission of the previous
signing-key pin. It intentionally creates a new provider identity. An upgrade with
a missing volume or signing-key pin fails instead of generating a replacement.
Direct Compose also treats the selected volume as external and refuses a typo.

## Preserve federation reputation across a verified URL move

After verifying that both provider addresses have the same Ed25519 and pinned PQ
signing identity, configure the Hub with an explicit operator-owned alias map:

```dotenv
AIMARKET_PEER_IDENTITY_ALIASES='{"https://modelmarket.dev/providers/symmartys":["https://modelmarket.dev/providers/emporion"]}'
```

This setting pools the provider's existing invocation, reputation and confirmed
delivery history when deriving trust. It does not change historical source URLs,
signatures or receipts. Use the exact URLs stored in history. Overlapping groups,
duplicate identities and invalid URLs fail validation; names and remote claims
never create aliases. With no setting, scoring retains its existing URL scope.

Preserve the existing peer's `first_seen` and key pins when replacing its catalogue
entry, then run the ordinary trust recomputation after a targeted crawl. Compare
against the original private backup: a newly created canonical peer is not a valid
baseline for checking metadata continuity. Keep the alias map in the persistent
Hub environment so later restarts and full crawls retain the same history scope.
