# Who counts as us: SELF and EXT traffic

[English](traffic-classes.md) · [Русский](traffic-classes.ru.md) · [Español](traffic-classes.es.md) · [Français](traffic-classes.fr.md) · [中文](traffic-classes.zh.md)

Every call the hub records is either **SELF** or **EXT**. The class appears in `/ai-market/v2/stats/live` (`traffic_class` on each event), on the home page (the `ext` / `self` tag, the filters, the ticker) and in the lifetime counters (`external_invocations`, `operator_self_invocations`). EXT is the number you quote as demand, so it must not contain your own traffic, and it must not lose a real customer either.

## The rule

- **SELF** is the hub itself and the components bound to it that belong to **its own ecosystem**: services you run for this hub, such as your desks, monitors, canaries and first-party providers.
- **EXT** is everybody else. That includes buyers and agents, other ecosystems, anyone who deploys this open-source code for themselves, and **outside services connected through a paid rail**, even when they run on your hardware. A game that buys capabilities for its players is a customer, not part of the ecosystem.

With no configuration the hub knows only itself: admin smoke tests, `local` and its own URL are SELF, and everything else is EXT. You add the rest of your ecosystem in one file, `ecosystem.json`.

## What decides the class

| Evidence | Applies to | Decided | Effect |
|---|---|---|---|
| The hub itself (admin Bearer smoke test, `local`, the hub's own URL) | any call | when read | always SELF |
| A **forwarded** call: another hub routed a buyer here (it sends `X-AIMarket-Routing-Hub` / `X-AIMarket-Buyer`, or a `hub-fed-…` trial visitor), or a seller operation another hub bought | any call | when written | never SELF on this hub |
| `external.networks`, `external.wallets` | any call | when written | EXT, whatever else matches |
| `external.accounts` | calls charged to a credit account | when read | EXT, whatever else matches |
| `self.accounts` | calls charged to a credit account (`X-API-Key`, a mandate, a job allowance) | when read | SELF |
| `self.wallets` | x402 calls: the wallet that paid, verified on chain (a payment-channel id arrives in a header and vouches for nothing) | when written | SELF |
| `self.networks` | only calls with **neither a payer nor a trial visitor**: the hub's MCP gateway and bare calls | when written | SELF |

The rows are checked in that order and the first match wins. So `external` always beats `self`, and a forwarded call is never SELF. One exception: an x402 payer verified on chain is evidence wherever it arrives, so `self.wallets` / `external.wallets` apply even inside a forward. A request from a peer that is not in `AIMARKET_TRUSTED_PROXIES` but carries `X-Forwarded-For`, `Forwarded` or `X-Real-IP` is a relay announcing itself, and counts as forwarded.

**"When read"** means that editing the file re-classifies history. Take an account out of `self.accounts`, and its past calls become EXT on the next page load. **"When written"** means the evidence (the caller's address, the paying wallet) is not stored. The hub judges it once, as the row is written, and keeps only the verdict. A server or wallet you add today classifies only calls made from now on. The row does remember WHICH entry vouched for it, so taking a mistaken entry out of the file turns those rows back into EXT.

## Why an address never vouches for a paid call

The hub's own plumbing makes your servers the direct caller of a lot of traffic that is not yours:

- a peer hub routing a stranger's purchase reaches this hub from **that hub's** address;
- a paid Studio step bought on another hub arrives from the **buying hub**;
- a subcontract child, funded by a stranger's allowance, is called by **your provider host**;
- a factory executor runs a browser visitor's free pipeline **from the factory host**.

If an address could make these SELF, real demand would disappear from EXT. So a paid call is judged by **who paid**, the account or the wallet, never by where it came from. The address rule only covers calls with no payer and no trial visitor: a trial visitor arriving from a server is almost always a relay. A forwarded call is classified by the hub that routed it, the one that saw the real buyer. Each hub's own feed therefore stays honest. When you add up several hubs, drop the rows with `traffic_basis: "forwarded"` so that one purchase is not counted twice.

## The file

**Where.** `AIMARKET_ECOSYSTEM_FILE` if set. Otherwise `ecosystem.json` next to the hub database (`AIMARKET_DB_PATH`); in the Docker image that is `/app/data/ecosystem.json`, on the data volume. Otherwise `./data/ecosystem.json`. Keep it on the server: it lists your servers and accounts, so it never belongs in a public repository. The repository ships [`examples/ecosystem.example.json`](../examples/ecosystem.example.json) with documentation-range addresses.

**Format.** JSON. Each entry is a string, or an object `{"value": "...", "note": "why this is here"}`. The hub ignores `note`, which is there for whoever edits the file next.

```json
{
  "version": 1,
  "self": {
    "accounts": [{"value": "acct_0123456789abcdef", "note": "demo desk"}],
    "networks": [{"value": "198.51.100.7", "note": "desks + monitoring host"}, "2001:db8:7::7"],
    "wallets":  [{"value": "0x1111111111111111111111111111111111111111", "note": "test buyer"}]
  },
  "external": {
    "accounts": [{"value": "acct_aaaaaaaaaaaaaaaa", "note": "a game we host: a customer"}],
    "networks": ["203.0.113.80"],
    "wallets":  []
  }
}
```

**Validation.**

- **Rejected file.** An unknown key, a wrong type, or a `version` other than `1` rejects the whole file. A misspelt `"netwroks"` would otherwise drop a whole list without a word.
- **Skipped values.** A single bad value is skipped and reported, and the rest of the file applies.
- **Refused networks.** The hub refuses networks that can never be one of your servers seen from inside the hub:
  - loopback, `0.0.0.0/8` and `::`;
  - RFC 1918 and CGNAT, `100.64.0.0/10`;
  - link-local, IPv6 unique-local and multicast;
  - IPv4-translation prefixes (NAT64 `64:ff9b::/96`, 6to4 `2002::/16`);
  - anything broader than an IPv4 `/24` or an IPv6 `/56`: list your servers, not your provider's block;
  - any network that contains an address in `AIMARKET_TRUSTED_PROXIES`.

  Those are exactly the addresses the MCP gateway, in-process bridges, docker gateways and proxies arrive from, carrying other people's calls. IPv4-mapped IPv6 (`::ffff:198.51.100.7`) is treated as the IPv4 address.
- **Both lists.** An entry that is in both lists counts as external.

**Changes apply without a restart.** The hub notices a modified file on the next call. If an edit makes the file invalid, the **last good version stays in force**, `status` becomes `invalid` and the error goes to the log. A typo must not flip your own traffic to EXT. Deleting the file returns the hub to the default rule.

**Check before you save.**

```bash
python -m aimarket_hub.ecosystem check /path/to/ecosystem.json
# exit 0 ok, 2 some entries refused, 1 rejected or missing
```

**On a Docker hub**, put the file in the data volume, make it readable by the hub's user (uid 10001), and check it with the hub's own environment:

```bash
docker cp ecosystem.json modelmarket-hub:/app/data/ecosystem.json
docker exec -u 0 modelmarket-hub chown 10001:10001 /app/data/ecosystem.json
docker exec modelmarket-hub python -m aimarket_hub.ecosystem check
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'   # status ok, a new loaded_at
```

Do not bind-mount the file on its own: an editor that saves by renaming leaves the container on the old copy. Include it in backups of the data volume. The last good version survives an invalid edit only until the next restart. Because account edits re-classify history, `external_invocations` is not monotonic: a dashboard that diffs it will see jumps when the registry changes.

`AIMARKET_OPERATOR_ACCOUNTS` (comma-separated account ids) still works. It is merged into `self.accounts`; with a file present the hub logs a warning, so keep the list in one place.

## What is published

- **Events.** Each event carries `traffic_class` (`operator_self` or `external`) and `traffic_basis`, which says why: `operator`, `account`, `address`, `wallet`, `forwarded`, `override` (an `external` entry), or `null` (a plain external call).
- **Purpose.** An event may carry `purpose`: a short label the caller sent with the invoke (`"purpose": "feed"`) to say why it made the call. It is the caller's own label and the hub does not check it. Only `[a-z][a-z0-9-]{0,23}` is kept; anything else is dropped, and the call is not refused. Empty means the caller sent none.
- **Summary.** `summary.traffic_policy` publishes how many entries each list has, where the rule came from (`default`, `env`, `file`, `file+env`), whether the file loaded (`absent`, `ok`, `partial`, `invalid`) and when.
- **Never published:** addresses, account ids, wallets and the file path. The stored verdict column, `caller_class`, does not leave the hub.

```bash
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '.summary.traffic_policy'
curl -s https://your-hub.example/ai-market/v2/stats/live | jq '[.events[] | {capability_id, purpose, traffic_class, traffic_basis}]'
```

## Before you list something as yours

- **A server.** List it only if its own processes call this hub as part of this hub's ecosystem. Never list a host that relays other people's requests:
  - another hub;
  - a gateway;
  - a factory executor;
  - a tenant or sandbox platform where other parties' code runs;
  - a self-hosted `aimarket-mcp`.

  Exclude such a server, or put it under `external.networks`.
- **IPv6.** List both the IPv4 and the IPv6 address of a dual-stack server.
- **Not the hub's own address.** Never list the public address of the host the hub runs on when that host also runs anything that relays others; calls the hub makes to its own public URL would turn SELF.
- **Proxy trust.** `AIMARKET_TRUSTED_PROXIES` must name your real reverse proxy (see [production deployment](production-deployment.md)). Without it every caller looks like the proxy, and the address rule matches nothing. The address is only as trustworthy as that list: any process that reaches the hub *from* a trusted proxy address (for example a host process going through a docker gateway) can name any client address. Keep the list to the reverse proxy, and do not use `self.networks` on a hub where untrusted code can reach it that way.
- **An account.** List the accounts your own components spend from. Never list an account you minted *for* a customer. On a hub with signup closed every account is operator-minted, including the customers'. Calls paid from a mandate or a job allowance carry the FUNDING account, so never hand a mandate or allowance of a listed account to an outside provider. Never list the account another hub uses at this hub either: its key carries other people's purchases.
- **A wallet.** List wallets that pay for your own tests and ecosystem traffic. Never list a hub, relay or peer-channel wallet that pays on behalf of others.

## History

Rows recorded before 3.15.0 have no stored verdict and are classified by their label alone. Editing an account re-classifies them like everything else. The address and wallet rules apply only to calls recorded after the entry was added.
