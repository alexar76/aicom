"""Run on Linux against the current Hub code with only a disposable SQLite database.

Writes an inspectable monetary trace. The one-dollar opening credit is a fake grant;
there is no wallet, chain transport, real USDC, provider invocation or money transfer.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import platform
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from aimarket_hub import credits, invoke_funding, mandates
from aimarket_hub.database import HubDatabase


def run_trace() -> dict[str, Any]:
    initial_mc = 100_000
    trace: list[dict[str, Any]] = []
    checks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="micky-ledger-trace-") as temporary:
        db = HubDatabase(Path(temporary) / "trace.db", database_url="")
        try:
            ledger = credits.CreditsLedger(db._conn)
            store = mandates.MandateStore(db._conn, "https://hub.test")
            opened = ledger.create_account(
                label="Micky controlled trace, fake grant only", grant_usd=1.0,
                grant_note="synthetic opening credit; no funds received",
            )
            account = opened["account_id"]

            def snapshot(step: str, operation: Any) -> dict[str, Any]:
                row = db._conn.execute(
                    "SELECT balance_mc, held_mc, spent_mc, collateral_mc, granted_mc, topped_up_mc "
                    "FROM credit_accounts WHERE account_id = ?", (account,),
                ).fetchone()
                raw = {field: int(row[field] or 0) for field in (
                    "balance_mc", "held_mc", "spent_mc", "collateral_mc", "granted_mc", "topped_up_mc")}
                holds = [dict(h) for h in db._conn.execute(
                    "SELECT receipt_id, amount_mc, status, created_at FROM credit_holds "
                    "WHERE account_id = ? ORDER BY receipt_id", (account,),
                ).fetchall()]
                held_total = sum(int(h["amount_mc"]) for h in holds if h["status"] == "held")
                assert all(value >= 0 for value in raw.values()), (step, raw)
                assert sum(raw[f] for f in ("balance_mc", "held_mc", "spent_mc", "collateral_mc")) == initial_mc, (step, raw)
                assert held_total == raw["held_mc"], (step, holds, raw)
                assert raw["granted_mc"] == initial_mc and raw["topped_up_mc"] == 0, (step, raw)
                entry = {
                    "step": step,
                    "operation_result": operation,
                    "account": ledger.account(account),
                    "raw_millicents": raw,
                    "holds": holds,
                    "stats": ledger.stats(),
                    "ledger_entries": ledger.recent(account, limit=100),
                    "invariants": {
                        "nonnegative_amounts": True,
                        "balance_plus_held_plus_spent_plus_collateral_mc": initial_mc,
                        "held_rows_equal_account_held_mc": True,
                        "paid_topups_mc": 0,
                    },
                }
                trace.append(entry)
                return entry

            snapshot("01_initial_fake_grant", {"fake_grant_usd": 1.0})

            result = ledger.hold(account, 0.20, "failed-call")
            assert not result.get("error"), result
            snapshot("02_hold_for_failed_call", result)
            result = ledger.release_hold("failed-call")
            assert result["released_usd"] == 0.20, result
            snapshot("03_release_after_failed_call", result)
            result = ledger.release_hold("failed-call")
            assert result == {"released_usd": 0.0, "already": "released"}, result
            snapshot("04_repeat_release_is_noop", result)
            checks.append("Failed hold returns 0.20 credit once; duplicate release is a no-op.")

            result = ledger.hold(account, 0.20, "successful-call")
            assert not result.get("error"), result
            snapshot("05_hold_for_successful_call", result)
            result = ledger.capture_hold("successful-call")
            assert result["captured_usd"] == 0.20, result
            snapshot("06_capture_after_successful_call", result)
            result = ledger.capture_hold("successful-call")
            assert result == {"captured_usd": 0.0, "already": "captured"}, result
            snapshot("07_repeat_capture_is_noop", result)
            checks.append("Successful capture records 0.20 spent once; duplicate capture is a no-op.")

            before = snapshot("08_before_overbudget_attempt", {"attempt_usd": 0.90})
            result = ledger.hold(account, 0.90, "overbudget-call")
            assert result.get("error"), result
            after = snapshot("09_overbudget_hold_refused", result)
            assert before["raw_millicents"] == after["raw_millicents"], (before, after)
            assert before["holds"] == after["holds"], (before, after)
            assert before["ledger_entries"] == after["ledger_entries"], (before, after)
            checks.append("0.90 hold with 0.80 available is refused without any account, hold or ledger mutation.")

            result = ledger.hold(account, 0.10, "abandoned-call")
            assert not result.get("error"), result
            snapshot("10_abandoned_call_held", result)
            stamp = "2000-01-01 00:00:00"
            db._conn.execute(
                "UPDATE credit_holds SET created_at = ? WHERE receipt_id = ?", (stamp, "abandoned-call"),
            )
            db._conn.commit()
            snapshot("11_artificially_age_hold", {"fixture_created_at": stamp, "timezone": "UTC"})
            created = datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp()
            count = invoke_funding.sweep_stale_credit_holds(
                credits_ledger=ledger, store=store, now=created + 3600.0,
            )
            assert count == 0, count
            assert ledger.hold_status("abandoned-call")["status"] == "held"
            snapshot("12_sweep_at_3600_seconds", {"released_holds": count, "fixture_age_s": 3600.0})
            count = invoke_funding.sweep_stale_credit_holds(
                credits_ledger=ledger, store=store, now=created + 3600.001,
            )
            assert count == 1, count
            assert ledger.hold_status("abandoned-call")["status"] == "released"
            snapshot("13_sweep_after_3600_seconds", {"released_holds": count, "fixture_age_s": 3600.001})
            count = invoke_funding.sweep_stale_credit_holds(
                credits_ledger=ledger, store=store, now=created + 7200.0,
            )
            assert count == 0, count
            final = snapshot("14_repeat_sweep_is_noop", {"released_holds": count, "fixture_age_s": 7200.0})
            assert final["raw_millicents"] == {
                "balance_mc": 80_000, "held_mc": 0, "spent_mc": 20_000,
                "collateral_mc": 0, "granted_mc": 100_000, "topped_up_mc": 0,
            }, final
            checks.append("Abandoned hold stays held at exactly 3600 seconds, releases after 3600 seconds, then sweeps idempotently.")
            checks.append("Every step conserves 100000 millicents; release restores service credit without reducing the operator liability through a payout.")
        finally:
            db.close()

    source_paths = {"trace_ledger": Path(__file__).resolve()}
    for module in (credits, invoke_funding, mandates):
        source_paths[module.__name__] = Path(inspect.getfile(module)).resolve()
    source_paths["HubDatabase"] = Path(inspect.getfile(HubDatabase)).resolve()
    return {
        "schema": "micky-credit-ledger-trace/1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "runtime": {"platform": platform.system(), "python": sys.version.split()[0]},
        "rail": "prepaid credits, current source, disposable SQLite with actual HubDatabase migrations",
        "funding": "1.00 synthetic grant, not a paid top-up or USDC transfer",
        "real_payment_or_chain_transport": False,
        "unit": {"millicents_per_usd": 100_000},
        "source_sha256": {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in source_paths.items()},
        "passed_checks": checks,
        "steps": trace,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/out/ledger-trace.json"))
    args = parser.parse_args()
    payload = run_trace()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.out), "steps": len(payload["steps"]),
                      "checks": len(payload["passed_checks"]), "status": "passed"}))
