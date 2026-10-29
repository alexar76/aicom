from __future__ import annotations

import argparse

from skopos.config import load_app_env

load_app_env()

from skopos.collector import collect_once
from skopos.config import load_config
from skopos.log_sources import resolve_log_sources
from skopos.security.collector import scan_all_servers


def _unrouted_credentials(cfg) -> list[dict]:
    from skopos.db import connect_for_config
    from skopos.node_ingest import unrouted_credentials

    con = connect_for_config(cfg)
    try:
        return unrouted_credentials(cfg, con)
    finally:
        con.close()


def _unrouted_message(cred: dict, config_path: str) -> str:
    return (
        f"'{cred['server_name']}' ({cred['key_id']}) is enrolled, but {config_path} has no "
        "agent-push entry for it, so every report it sends is refused. Restore the entry, "
        "or retire the host with node-revoke."
    )


def main() -> int:
    ap = argparse.ArgumentParser(prog="skoposctl", description="SKOPOS collector control")
    ap.add_argument("--config", default="./servers.yaml", help="Path to servers.yaml")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("collect", help="Collect once from all servers")
    sub.add_parser("discover", help="List HTTP log sources discovered on servers")
    sub.add_parser("security-scan", help="Run security probe + audit on all servers")

    p_push = sub.add_parser(
        "momus-push",
        help="Send the newest security findings to MOMUS, so they reach the fix loop")
    p_push.add_argument("--server", action="append", default=None,
                        help="Only this server (repeatable); default: every scanned server")
    p_push.add_argument("--resend", action="store_true",
                        help="Send even a snapshot MOMUS was already told about")
    p_asn = sub.add_parser("backfill-asn", help="Fill asn/asn_org for existing rows from the iptoasn TSV")
    p_asn.add_argument("--tsv", default=None, help="Path to ip2asn-combined.tsv (default: auto-discover)")

    sub.add_parser("doctor", help="Report collection posture problems")

    p_trust = sub.add_parser("trust-host", help="Record a host's SSH key after verifying its fingerprint")
    p_trust.add_argument("--host", required=True)
    p_trust.add_argument("--port", type=int, default=22)
    p_trust.add_argument("--yes", action="store_true", help="Skip the fingerprint confirmation")

    p_ticket = sub.add_parser("node-ticket", help="Mint a single-use enrollment ticket for a host")
    p_ticket.add_argument("--server", required=True)

    p_inst = sub.add_parser("node-installer", help="Render the agent installer for a host")
    p_inst.add_argument("--server", required=True)
    p_inst.add_argument("--base-url", required=True, help="https URL the agent reports to")
    p_inst.add_argument("--out", default=None, help="Write here instead of stdout")
    p_inst.add_argument("--containers", default="", help="Comma-separated container allow-list")
    p_inst.add_argument("--interval", type=int, default=300)
    p_inst.add_argument("--no-privileged", action="store_true",
                        help="Logs only: skip the root dump, so the host reports no posture")

    sub.add_parser("node-list", help="List enrolled agents")
    sub.add_parser(
        "node-check",
        help="Exit 1 if an enrolled agent has no agent-push entry (its reports would be refused)")

    p_revoke = sub.add_parser("node-revoke", help="Revoke an agent credential")
    p_revoke.add_argument("--key-id", required=True)

    args = ap.parse_args()

    cfg = load_config(args.config)
    if args.cmd == "collect":
        res = collect_once(cfg)
        for r in res:
            print(f"{r.server_name}: fetched={r.fetched_lines} inserted={r.inserted_rows} sources={len(r.log_paths)}")
            for p in r.log_paths:
                print(f"  - {p}")
        return 0

    if args.cmd == "discover":
        for s in cfg.servers:
            sources = resolve_log_sources(s)
            print(f"{s.name} ({s.ssh.host}:{s.ssh.port}) — {len(sources)} source(s)")
            for src in sources:
                print(f"  [{src.kind}/{src.parser}] {src.id}")
        return 0

    if args.cmd == "backfill-asn":
        from skopos.backfill import backfill_asn

        target = cfg.database_url or cfg.db_path
        updated = backfill_asn(target, tsv_path=args.tsv or cfg.asn_tsv_path)
        print(f"asn backfill: updated={updated}")
        return 0

    if args.cmd == "doctor":
        from skopos.config import config_warnings

        problems = config_warnings(cfg)
        try:
            problems += [_unrouted_message(c, args.config) for c in _unrouted_credentials(cfg)]
        except Exception:  # noqa: BLE001 - doctor reads config first; the database is a bonus
            pass
        for p in problems:
            print(f"  ! {p}")
        if not problems:
            print("No collection posture problems found.")
        return 0

    if args.cmd == "trust-host":
        import base64
        import hashlib

        from skopos.ssh import remember_host_key, scan_host_key

        key = scan_host_key(args.host, args.port)
        fingerprint = base64.b64encode(hashlib.sha256(key.asbytes()).digest()).decode().rstrip("=")
        print(f"{args.host}:{args.port} offers a {key.get_name()} key")
        print(f"  SHA256:{fingerprint}")
        if not args.yes:
            # Recording a key without looking at it is trust-on-first-use with
            # extra steps; the whole point is that a human compared it.
            print("Compare this against the host itself:")
            print("  ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub")
            if input("Record this key? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Not recorded.")
                return 1
        path = remember_host_key(args.host, args.port, key)
        print(f"Recorded in {path}")
        return 0

    if args.cmd == "node-ticket":
        from skopos.db import connect_for_config
        from skopos.node_store import create_ticket

        if not any(s.name == args.server for s in cfg.servers):
            print(f"No server named '{args.server}' in {args.config}")
            return 2
        con = connect_for_config(cfg)
        try:
            ticket = create_ticket(con, args.server)
        finally:
            con.close()
        print(ticket)
        return 0

    if args.cmd == "node-installer":
        from skopos.node_installer import containers_for, log_roots_for, render_installer

        server = next((s for s in cfg.servers if s.name == args.server), None)
        if server is None:
            print(f"No server named '{args.server}' in {args.config}")
            return 2
        # An explicit --containers wins; otherwise take what the server config
        # already says, so the installer matches the host it is for.
        containers = tuple(c.strip() for c in args.containers.split(",") if c.strip())
        script = render_installer(
            base_url=args.base_url,
            server_name=args.server,
            # An agent-ssh host must not get a push installer: it would try to
            # enroll, and would never install the forced command it needs.
            push=(server.transport != "agent-ssh"),
            log_roots=log_roots_for(server),
            containers=containers or containers_for(server),
            interval_s=args.interval,
            privileged=not args.no_privileged,
        )
        if args.out:
            from pathlib import Path

            Path(args.out).write_text(script, encoding="utf-8")
            print(f"wrote {args.out}")
        else:
            print(script)
        return 0

    if args.cmd == "node-list":
        from skopos.db import connect_for_config
        from skopos.node_store import list_credentials, secrets_are_sealed

        con = connect_for_config(cfg)
        try:
            rows = list_credentials(con)
        finally:
            con.close()
        if not secrets_are_sealed():
            print("! SKOPOS_NODE_SECRET_KEY is unset — node secrets are stored unencrypted\n")
        if not rows:
            print("No agents enrolled.")
            return 0
        for r in rows:
            state = "revoked" if r["revoked_at_utc"] else "active"
            print(
                f"{r['key_id']}  {r['server_name']:<20} {state:<8} "
                f"seq={r['last_seq']:<6} reports={r['reports_total']:<6} "
                f"last={r['last_seen_at_utc'] or 'never'} agent={r['agent_version'] or '-'}"
            )
        return 0

    if args.cmd == "node-check":
        # 0 = every agent is routed, 1 = some are not, 2 = could not tell. A deploy
        # refuses on 1 only, so a database that is not up yet does not block it.
        try:
            unrouted = _unrouted_credentials(cfg)
        except Exception as exc:  # noqa: BLE001 - reported, and distinct from "found some"
            print(f"node-check: could not read enrolled agents ({type(exc).__name__})")
            return 2
        for c in unrouted:
            print(f"  ! {_unrouted_message(c, args.config)}")
        if not unrouted:
            print("Every enrolled agent has an agent-push entry.")
        return 1 if unrouted else 0

    if args.cmd == "node-revoke":
        from skopos.db import connect_for_config
        from skopos.node_store import revoke_credential

        con = connect_for_config(cfg)
        try:
            ok = revoke_credential(con, args.key_id)
        finally:
            con.close()
        print("revoked" if ok else "not found, or already revoked")
        return 0 if ok else 1

    if args.cmd == "momus-push":
        # After a scan, not instead of one: this only forwards what the last scan already
        # found. MOMUS decides what becomes a ticket; the autopilot decides what ships.
        from skopos.db import connect_for_config
        from skopos.security.momus_push import push_latest

        con = connect_for_config(cfg)
        try:
            results = push_latest(con, server_names=args.server, resend=args.resend)
        finally:
            con.close()
        failed = 0
        for r in results:
            if r.pushed:
                print(f"{r.server_name}: sent snapshot={r.snapshot_id} "
                      f"findings={r.findings_sent} imported={r.imported}")
            else:
                # "Nothing new" is not a failure — a fleet that has not been rescanned
                # since the last push is the normal steady state.
                skipped = r.reason.startswith("already sent")
                print(f"{r.server_name}: {'skipped' if skipped else 'FAILED'} — {r.reason}")
                if not skipped:
                    failed += 1
        return 1 if failed else 0

    if args.cmd == "security-scan":
        results = scan_all_servers(cfg)
        for r in results:
            if r.ok:
                print(
                    f"{r.server_name}: ok findings={r.findings_count} "
                    f"knocks_inserted={r.knocks_inserted} snapshot_id={r.snapshot_id}"
                )
            else:
                print(f"{r.server_name}: ERROR {r.error}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
