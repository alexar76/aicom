#!/usr/bin/env python3
"""Require line/branch coverage for named financial boundaries, without hiding global gaps."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Floors apply to functions, not whole packages or an artificially narrowed global percentage.
TARGETS = (
    ("web/backend/services/checkout_quote.py", "seal_quote", 100, 100),
    ("web/backend/services/payment_claim.py", "verify_claim", 100, 100),
    ("web/backend/api/payment.py", "_complete_checkout", 100, 100),
    ("web/backend/api/payment.py", "_confirm_payment", 100, 100),
    ("web/backend/services/commerce.py", "CommerceService.create_order_and_license", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.refund_withdrawal", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.charge", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.withdraw_to_chain", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.hold", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.spend_hold", 100, 100),
    ("core/uni/wallet.py", "UniWalletService.release_hold", 100, 100),
    ("core/uni/wallet.py", "UniWalletService._credit", 100, 100),
    ("core/uni/receipts.py", "issue_receipt", 100, 100),
)


def check_report(report: dict[str, Any]) -> list[str]:
    """Reject missing scope/counters as well as regressions below either floor."""
    if report["meta"].get("branch_coverage") is not True:
        raise ValueError("Branch coverage is required; rerun the suite with the repository coverage config")
    failures = []
    for filename, function, line_floor, branch_floor in TARGETS:
        try:
            summary = report["files"][filename]["functions"][function]["summary"]
        except KeyError as exc:
            raise ValueError(f"Required coverage scope is missing: {filename}:{function}") from exc
        counts = [summary[key] for key in ("covered_lines", "num_statements", "covered_branches", "num_branches")]
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError(f"Invalid coverage counters for {function}")
        lines, total_lines, branches, total_branches = counts
        if not total_lines or lines > total_lines or branches > total_branches:
            raise ValueError(f"Invalid coverage totals for {function}")
        line_pct = 100 * lines / total_lines
        branch_pct = 100 * branches / total_branches if total_branches else 100.0
        verdict = f"{filename}:{function}: lines {line_pct:.1f}% / branches {branch_pct:.1f}%"
        print(verdict)
        # Compare counts, not rounded display percentages.
        if lines * 100 < line_floor * total_lines or branches * 100 < branch_floor * total_branches:
            failures.append(f"{verdict}; required {line_floor}% / {branch_floor}%")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", nargs="?", type=Path, default=Path("coverage.json"))
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"))
        failures = check_report(report)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, AttributeError) as exc:
        print(f"Payment coverage check could not validate the report: {exc}", file=sys.stderr)
        return 2
    if failures:
        print("Payment coverage FAILED:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"Payment coverage passed ({len(TARGETS)} named functions; this does not certify unmeasured paths).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
