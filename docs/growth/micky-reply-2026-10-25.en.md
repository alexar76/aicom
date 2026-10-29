Following up, Micky: we checked the current Hub source with synthetic funds on Linux. All 146 checks passed; this was not a live-payment test.

The credits path reserves before calling the provider and captures the fixed reserved price on success. Tested provider failures release it. Concurrent holds cannot exceed the balance, and repeated capture/release cannot move it twice. Output-metered pricing and capture above the hold are not implemented.

A timeout can release credit after the provider has already acted. Our retry control duplicated that external effect: releasing money does not roll back work or guarantee exactly-once execution.

Ordinary abandoned holds become eligible for recovery after one hour; the default sweep runs every two minutes. That is recovery policy, not an exact client deadline. Verification and allowance holds have separate lifecycles.

You're right about the key: it has no automatic expiry or dollar-per-hour cap. IP request throttling is not a spending limit. Signed mandates provide per-call, UTC-calendar-day and total budgets, plus expiry, when required for the account.

Finally, release/refund restores service credit; it does not send USDC back. The unused balance remains the operator's liability, and a cash refund requires an operator-arranged transfer.
