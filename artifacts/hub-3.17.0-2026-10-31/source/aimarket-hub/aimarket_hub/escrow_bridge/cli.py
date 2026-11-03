"""Operator entry point for the escrow bridge.

    python -m aimarket_hub.escrow_bridge.cli status
    python -m aimarket_hub.escrow_bridge.cli plan
    python -m aimarket_hub.escrow_bridge.cli submit --yes
    python -m aimarket_hub.escrow_bridge.cli confirm
    python -m aimarket_hub.escrow_bridge.cli show <receipt_id>
    python -m aimarket_hub.escrow_bridge.cli verify <escrow_channel_id> --wallet 0x… --usd 5

Submission is a deliberate act, not a schedulable default. ``plan`` is safe to run on a
timer and is what an operator should look at first; ``submit`` additionally requires the
configured strategy, the confirmation phrase in the environment, AND ``--yes`` on the
command line — three independent things, so no single mistake starts moving money.

Exit codes: 0 success, 1 refused/blocked (an operator has something to fix), 2 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from aimarket_hub.escrow_bridge import config, escrow_verify, mirror, signer as signer_mod, store
from aimarket_hub.escrow_bridge.errors import BridgeError


def _emit(payload: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))
        return
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, (dict, list)):
                print(f"{key}:")
                print("  " + json.dumps(value, ensure_ascii=False, default=str))
            else:
                print(f"{key}: {value}")
    else:
        print(payload)


def _report_lines(report: mirror.MirrorReport) -> None:
    mode = "PLAN (nothing sent)" if report.dry_run else f"SUBMIT via {report.strategy}"
    print(f"mode: {mode}")
    print(f"scanned: {report.scanned}")
    for outcome, count in sorted(report.outcomes.items()):
        print(f"  {outcome}: {count}")
    for row in report.rows:
        extra = ""
        if row.get("amount_usd") is not None:
            extra += f" ${row['amount_usd']}"
        if row.get("tx_hash"):
            extra += f" tx={row['tx_hash']}"
        print(f"  [{row['outcome']}] {row['receipt_id'][:14]}…{extra}: {row['detail']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aimarket-escrow-bridge",
        description="Mirror off-chain channel debits onto AIMarketEscrow (opt-in).",
    )
    # Shared flags live on a parent parser so they work in BOTH positions — an operator
    # typing `status --json` should not get a usage error for putting a global flag where
    # it reads naturally. SUPPRESS keeps an unspecified subcommand flag from overwriting
    # the value given before the subcommand.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="machine-readable output")
    common.add_argument("--db", default=argparse.SUPPRESS,
                        help="authorization store path override")
    common.add_argument("--limit", type=int, default=argparse.SUPPRESS,
                        help="max authorizations per pass (default 200)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--db", default="", help="authorization store path override")
    parser.add_argument(
        "--limit", type=int, default=200, help="max authorizations per pass (default 200)"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", parents=[common],
                   help="Configuration, signer, queue and what is still owed")
    sub.add_parser("plan", parents=[common],
                   help="Simulate every pending authorization; send nothing")
    submit_p = sub.add_parser("submit", parents=[common],
                              help="Simulate AND broadcast (requires --yes)")
    submit_p.add_argument(
        "--yes", action="store_true",
        help="confirm on the command line that this may move funds",
    )
    sub.add_parser("confirm", parents=[common],
                   help="Resolve broadcast authorizations by reading receipts")
    show_p = sub.add_parser("show", parents=[common], help="One authorization")
    show_p.add_argument("receipt_id")
    verify_p = sub.add_parser("verify", parents=[common],
                              help="Check an escrow channel backs a credit (read-only)")
    verify_p.add_argument("escrow_channel_id")
    verify_p.add_argument("--wallet", required=True, help="the depositor the caller claims")
    verify_p.add_argument("--usd", required=True, type=float, help="credit to be backed")

    args = parser.parse_args(argv)
    as_json = bool(getattr(args, "json", False))

    try:
        # `status`, `show` and `verify` are read-only and must work on a hub that has not
        # enabled the bridge — that is exactly when an operator is trying to understand it.
        needs_enabled = args.command in ("plan", "submit", "confirm")
        if needs_enabled and not config.enabled():
            _emit(
                {
                    "error": "bridge disabled",
                    "detail": "set AIMARKET_ESCROW_BRIDGE_ENABLED=1 to mirror settlements",
                    "config": config.describe(),
                },
                as_json=as_json,
            )
            return 1

        if args.command == "verify":
            funding = escrow_verify.verify_funding(
                channel_id=args.escrow_channel_id,
                claimed_wallet=args.wallet,
                deposit_usd=args.usd,
            )
            _emit({"verified": True, **funding.as_dict()}, as_json=as_json)
            return 0

        # Read-only commands must not CREATE the store: inspecting a hub that never
        # enabled the bridge should leave nothing behind.
        read_only = args.command in ("status", "show")
        try:
            authorizations = store.AuthorizationStore(
                getattr(args, "db", "") or None, create=not read_only
            )
        except store.StoreError:
            _emit(
                {
                    "config": config.describe(),
                    "signer": signer_mod.build_signer().name,
                    "store": "absent — no authorization has been recorded yet",
                },
                as_json=as_json,
            )
            # `status` on an empty hub is a healthy answer; `show` was asked about one
            # specific receipt and could not find it, which a script should notice.
            return 1 if args.command == "show" else 0

        if args.command == "show":
            row = authorizations.get(args.receipt_id)
            if row is None:
                _emit({"error": "not found", "receipt_id": args.receipt_id}, as_json=as_json)
                return 1
            _emit(row.as_dict(), as_json=as_json)
            return 0

        if args.command == "status":
            snapshot = {
                "config": config.describe(),
                "signer": signer_mod.build_signer().name,
                "store": authorizations.stats(),
                "queue": [r.as_dict() for r in authorizations.unresolved(limit=getattr(args, "limit", 200))],
            }
            _emit(snapshot, as_json=as_json)
            return 0

        # Plan mode is forced for `plan` regardless of how submission is configured, so
        # the safe command stays safe on a hub that is fully set up to broadcast.
        if args.command == "plan":
            engine = mirror.Mirror(
                authorizations=authorizations, signer=signer_mod.PlanOnlySigner()
            )
            report = engine.run(limit=getattr(args, "limit", 200))
        elif args.command == "submit":
            if not args.yes:
                _emit(
                    {
                        "error": "refused",
                        "detail": "submit moves funds — re-run with --yes once you have "
                                  "reviewed `plan` output",
                    },
                    as_json=as_json,
                )
                return 1
            policy = config.submit_policy()
            if not policy.may_broadcast:
                _emit(
                    {
                        "error": "refused",
                        "detail": policy.reason or (
                            "submission strategy is 'plan'; nothing would be sent"
                        ),
                        "config": config.describe(),
                    },
                    as_json=as_json,
                )
                return 1
            engine = mirror.Mirror(authorizations=authorizations)
            report = engine.run(limit=getattr(args, "limit", 200))
        else:  # confirm
            engine = mirror.Mirror(authorizations=authorizations)
            report = engine.confirm(limit=getattr(args, "limit", 200))

        if as_json:
            _emit(report.as_dict(), as_json=True)
        else:
            _report_lines(report)
        # A pass that could not move anything forward is worth a non-zero exit so a cron
        # or a runbook step surfaces it instead of looking healthy.
        stuck = report.outcomes.get(mirror.OUTCOME_BLOCKED, 0) + report.outcomes.get(
            mirror.OUTCOME_REFUSED, 0
        )
        return 1 if stuck and not (
            report.outcomes.get(mirror.OUTCOME_SUBMITTED)
            or report.outcomes.get(mirror.OUTCOME_CONFIRMED)
            or report.outcomes.get(mirror.OUTCOME_PLANNED)
        ) else 0

    except BridgeError as exc:
        _emit({"error": type(exc).__name__, "detail": str(exc)}, as_json=as_json)
        return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
