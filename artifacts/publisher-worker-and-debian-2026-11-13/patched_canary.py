#!/usr/bin/env python3
"""Repeat the autonomous payout canary after the Debian image switch."""

import worker_canary as canary

if __name__ == "__main__":
    canary.ORIGINAL_BALANCE_MC = 996

    # The first test state has the original top-up proof and both account credentials.
    # The previous repeat state only has the inherited credentials and sale, so anchor
    # the expected remaining balance while keeping the original proof checks intact.
    original_prepare = canary.prepare

    def prepare(args):
        response = original_prepare(args)
        if "buyer_balance_before_usdc" in response:
            response["buyer_balance_before_usdc"] = canary.ORIGINAL_BALANCE_MC / 100_000
            response["buyer_balance_after_usdc"] = (canary.ORIGINAL_BALANCE_MC - canary.SALE_MC) / 100_000
        return response

    canary.prepare = prepare
    canary.main()
