# Multica QA egress isolation

This is deployment configuration for Multica's Linux Docker host, separate from WARDEN's tool checks. It does not
patch or deploy an upstream Multica daemon. An agent gets only its internal backend API and an egress proxy;
the host prevents direct networking and access to host-local receivers. The proxy restricts the destination host,
while host rules restrict its transport ports. Allowed services can still carry secrets: keep credentials out of
QA and apply the [result gate](../README.md) before storing or publishing output.

Local source, 10 November 2026. The tests below validate the merge, rules and probe behavior. No Docker daemon was
available in the development workspace, so the proxy image was not built and these rules were not applied to a
host. These files do not establish a successful network acceptance run on `178.62.243.71` or any other server.

## Requirements and deployment scope

- Linux Docker Engine with bridge networking and the **iptables Docker firewall backend** for the supplied host
  plan. Docker's nftables backend needs a separately reviewed table with `input` and `forward` hooks; the generator
  refuses that backend. The `iptables-nft` command frontend is compatible with Docker's iptables backend; it is
  different from selecting Docker's experimental nftables backend.
- Docker Compose **2.24.4 or later**: `!override` removes the daemon's old networks, ports and added capabilities
  instead of merging them. A normal mapping merge can accidentally keep its direct route out.
- Existing Compose services named `daemon` and `backend`. Adapt the template if the deployment uses other names.
  The backend API here is TCP 8080. Preserve its existing app/database networks and add `qa_agent`; do not attach
  the daemon to those networks. No database, Docker socket, host namespace or host root mount belongs in the daemon.
- Unused dedicated subnets `10.250.0.0/24`, `10.251.0.0/24` and bridge names `br-multica-qa`, `br-multica-out`. If they
  collide, change **both** the Compose overlay, config checker and generated rules before deployment.
- The daemon runs as uid/gid 1000; its workspace/home volumes must support that user. Its image must contain
  Node.js 20+ for the acceptance probe. Install QA dependencies in the image, without a runtime npm-registry allow.
- A reviewed public IPv4 DNS resolver for the proxy (`QA_DNS_IP`). Daemon DNS is set to loopback; service-name
  discovery remains Docker-local. Verify that no external resolution is forwarded in the actual Docker version.
- Root-owned configuration and parent directories that the agent cannot replace. The proxy allowlist is mounted
  read-only. Docker image/application secrets are not a replacement for separate per-job credential permissions.

The example `Dockerfile` starts from `ubuntu:24.04` and installs the distribution's Tinyproxy and CA certificates.
Before rollout, record the resolved base digest, image ID and `/tinyproxy-package-version.txt`, run image security
checks, and pin the reviewed image for that deployment. An unpinned distribution tag/package mirror is not a
reproducible artifact. No image digest or current installed package version is claimed here.

## Prepare and inspect the merged configuration

On the deployment host, create an operator-owned allowlist, then edit it to contain only the exact hosts required
by that QA job. `allow.example` starts with **no allowed hosts**; its commented names are syntax examples. Obtain
the actual dev/prod names from the service owner. Do not invent production addresses, grant `*.github.com`, permit
GitHub writes/SSH, or add the whole npm registry to make tests run. Use prebuilt dependencies and narrow API scopes.

```sh
sudo install -d -o root -g root -m 0755 /etc/multica/egress
sudo install -o root -g root -m 0644 multica/security/egress/allow.example /etc/multica/egress/allow
sudoedit /etc/multica/egress/allow
```

Set these task-specific variables to the actual paths and approved resolver; the overlay requires them and will
refuse to render if one is missing:

```sh
export QA_EGRESS_DIR="$PWD/multica/security/egress"
export QA_ALLOWLIST_FILE=/etc/multica/egress/allow
export QA_DNS_IP=9.9.9.9
```

`9.9.9.9` is an example public resolver, not a deployment decision. Resolve and record which firewall backend is
configured in `dockerd` arguments and daemon configuration. Check the route table and existing Docker networks for
subnet collisions. Use a base Compose file path appropriate to the installation:

```sh
docker compose -f /opt/multica/docker-compose.yml -f "$QA_EGRESS_DIR/compose.egress.yaml" config --format json |
  python3 "$QA_EGRESS_DIR/check-config.py" --allowlist "$QA_ALLOWLIST_FILE"
```

Do not print or save the full merged configuration in a report: it may include environment credentials. The checker
consumes JSON from stdin and emits only a generic result. It checks this template's selected isolation properties;
it is not an audit of arbitrary mounts, application configuration, credentials or malicious images. The
`--allow-nonroot-owner` flag is only for local fixture validation, never deployment acceptance.

## Host enforcement and rollout

Generate a plan for review; this command **prints shell text and changes nothing**:

```sh
python3 "$QA_EGRESS_DIR/render-firewall.py" --backend iptables --dns-ip "$QA_DNS_IP" > /tmp/multica-qa-firewall.sh
sh -n /tmp/multica-qa-firewall.sh
```

Review the generated script alongside the merged Compose configuration, existing firewall manager and Docker
version. Stop QA jobs before applying it on the Linux host. It builds dedicated chains before linking them;
existing `MCQA_*` chains cause refusal so an installation is not silently overwritten. It verifies bridge
netfilter is enabled and refuses a detected Docker nftables table. Preserve out-of-band host access during rollout.

The plan covers separate paths:

| Path | Enforcement |
|---|---|
| Daemon to proxy | Only `10.250.0.20:8888` |
| Daemon to backend | Only `10.250.0.30:8080` |
| Daemon to any other forwarded address | Drop in a dedicated chain reached before Docker's iptables rules |
| Agent/proxy networks to host sockets, including Docker gateway receivers | Drop in host `INPUT`, independent of forwarding |
| Proxy to external services | Only TCP 443, plus TCP/UDP 53 to the selected DNS resolver |
| Proxy to private, link-local or metadata destinations | Drop; an allowed domain resolving there is not an exemption |
| IPv6 from these dedicated bridges | Disabled in containers and dropped at host `INPUT`/`FORWARD` |

`ConnectPort 443` restricts **CONNECT only**. Tinyproxy also supports ordinary HTTP proxy requests; the host's proxy
egress restriction closes other ports such as 80 and 8443. TCP port 443 is not proof that the payload is HTTPS, and
the proxy does not inspect encrypted bodies or constrain repository names/API operations. SSH does not use
`HTTP_PROXY` automatically; direct SSH remains blocked rather than being separately allowed.

Persist these dedicated rules with the host's firewall manager **after Docker is available** and ensure they survive
recreation/reboot. Do not flush Docker's tables or disable Docker's firewall management. An ordinary ufw policy or
`internal: true` by itself does not establish the host-gateway or DNS boundary. Review backend API authentication,
authorization, SSRF and relay behavior: an allowed backend must not be an unrestricted network proxy for the agent.

After building and pinning the proxy image, recreate only the affected services during the stopped-job window,
using the same base file and overlay used for validation. Keep tasks stopped until the host/proxy checks below,
WARDEN check and result gate pass. This repository does not execute that rollout.

For removal/update, stop the daemon's tasks first. Remove only the jump rules to `MCQA_INPUT`, `MCQA_FORWARD`,
`MCQA6_INPUT`, `MCQA6_FORWARD`, then flush/delete those dedicated chains through the same firewall manager. Never
flush unrelated chains or leave tasks running while the host protection is absent. Keep the internal-network
configuration in place until its replacement has passed acceptance.

## Acceptance from the real daemon

`verify-egress.py` runs probes through `docker exec`, independent of the agent/model and of proxy environment
variables. It sends only unauthenticated connection/header probes and a random DNS label. It does not read `.env`,
send a token, alter rules, create containers or print response bodies. A TCP connection **counts as reachable even
if the server never replies**; `curl` timing out is not accepted as evidence that transmission failed.

Prepare controlled listeners before running it:

- A receiver on the **actual host gateway** and port 9999, reachable from the host control path. For the reported
  topology this was `172.18.0.1:9999`; do not assume a recreated network uses the same gateway. Use a persistent
  listener (`nc -lk` on implementations supporting it, or an equivalent controlled service), because the control
  check itself opens and closes a connection. Check receiver logs as well as the script result.
- A controlled public IPv4 endpoint reachable from the host on TCP 443 and 22. If available, also provide a known
  reachable public IPv6 endpoint on TCP 443. Omitted IPv6 yields `ipv6_live_checked: false`, not an IPv6 test pass.
- A temporary, exact-host allowlisted test server reachable from the host on ports 80 and 8443, returning ordinary
  HTTP 200 headers on those ports. The daemon's corresponding proxy requests must fail. Remove the temporary
  allowlist entry after testing. Without listeners, connection failures would be inconclusive.
- A real approved HTTPS health URL with valid TLS, no credentials/query parameters, and the backend health route.
  Any HTTPS status from 200 through 499 establishes transport only; a 401 does not establish authenticated QA.

Run the CLI with the actual values; `--help` lists every required argument:

```sh
python3 "$QA_EGRESS_DIR/verify-egress.py" --help
```

It first checks receiver reachability from the host. Missing control listeners give exit 3 (inconclusive), probe
execution failures give exit 2, any failed isolation check gives exit 1, and passing its bounded probe set gives
exit 0. Retain the boolean JSON as evidence. Independently confirm the test host is on the intended exact allowlist.

Some Tinyproxy builds return HTTP 500 when an outbound TCP connection is rejected. The generic probe conservatively
reports that status as a failure: HTTP 500 alone could instead mean DNS or service failure. Before accepting it as
a blocked-port result, record a successful host-side connection to that exact test endpoint and a before/after
increase in the corresponding `MCQA_FORWARD` TCP reject counter during that one request. Do not classify arbitrary
HTTP 500 responses as security successes. The attested deployment's separate counter-proof receipt follows this
procedure.

Also test Docker's embedded resolver with a unique label under an operator-controlled authoritative DNS zone,
and verify that no query arrives in its logs. The direct external-DNS probe alone does not prove that Docker's DNS
forwarder cannot relay a query. Test any IPv6 link-local path enabled by the host. Re-run after host/Docker restart,
then run an ordinary QA job and submit a sanitized report through the allowed backend.

Network acceptance and WARDEN acceptance are separate. For the original fake-token case, record a WARDEN **pre-tool
deny before the first curl executes**, separately from the firewall dropping that curl. Verify that final result,
summary, errors, comments and logs contain no canary credential. A network pass alone does not fix final-output
storage or demonstrate that the WARDEN decision was enforced.

## Local checks and sources

```sh
python3 -m unittest discover -s multica/security/egress/tests -v
node --test multica/security/egress/tests/probe.test.mjs
node --check multica/security/egress/probe.mjs
```

The Python suite parses a merged Compose fixture without starting Docker and rejects accidental direct networks,
capabilities, alternate proxy exclusions and socket mounts. Node tests use temporary loopback listeners, including
a receiver that accepts a connection but never responds. They require permission to bind a loopback socket.

Configuration semantics were checked against official documentation on 10 November 2026:
[Docker firewall integration](https://docs.docker.com/engine/network/packet-filtering-firewalls/),
[Docker iptables](https://docs.docker.com/engine/network/firewall-iptables/),
[Docker nftables](https://docs.docker.com/engine/network/firewall-nftables/),
[Compose merge](https://docs.docker.com/reference/compose-file/merge/), and
[Tinyproxy configuration](https://tinyproxy.github.io/).
