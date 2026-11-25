# Reply to Cross (ReloadPi) — DRAFT 2026-11-25, owner sends in the same thread

Their answer (2026-11-25) to our 2026-11-24 letter: states PROCESSING → FULFILLED | FULFILLMENT_FAILED | EXPIRED;
auto refund to the payer in USDC on Base; refund auth = payment txHash + order state; no sandbox (Base mainnet only,
cheapest test = a real $4 eSIM); offers a walkthrough of a failed order. Prefers replies in this thread over a new Gmail mail.

Checked 2026-11-25:
- https://api.reloadpi.com/.well-known/x402 `refund_policy` v0.2: automatic for FULFILLMENT_FAILED and EXPIRED, 24 h
  window, idempotency required, delivered items non-refundable. Matches what they wrote.
- sF1nX/x402-signals issue #1: three refund tx (0x7539e7, 0x7658ce, 0x0b0298) from three separate $1.61 topups,
  not a retry loop; x402-signals v0.2.0 cites ReloadPI as the first field implementation.
- Our kit (esim-kit/rails/src/refund.js): refund keyed by a stable reference, reserved before the first call,
  EIP-3009 nonce saved before settle; a reserved refund with no result refuses a retry ("reconcile its settlement
  before retrying") and waits for the operator. So we have the same open gap as theirs (no automatic refund reconciler).
- Not checked: the three refund transactions on Base.

No live purchase without the owner's decision (their $4 eSIM = moving real funds).

## Text

Hi Cross,

Thanks for the detailed answer. Replying here is fine for us.

The walkthrough from the on-chain examples is enough to start. Could you send, for one of the three topup orders in
x402-signals issue #1, the order id, the purchase tx, the time it entered FULFILLMENT_FAILED and the refund tx? We will
read the chain side ourselves and line it up with the states in your status endpoint.

On the retry gaps you listed, we are in the same place. Our kit keys each refund by a stable reference, reserves it
before the first external call, and refuses a second attempt while an earlier one has no result. An uncertain refund
goes to the operator, and we have no automatic reconciler either. One thing that may help with "a send that throws
after broadcast": we pay refunds as an EIP-3009 transferWithAuthorization and save the authorization nonce before
submitting. A reconciler can then ask the USDC contract authorizationState(payer, nonce). If it returns true, the
transfer went through. If it is still unused, resubmitting the same signed authorization can move the money at most
once. If you send refunds as plain transfers, the equivalent is to persist the signed raw transaction and its nonce
before broadcasting it.

Agreed that delivered eSIMs are not refundable. The case we care about is the order that fails at the carrier after
payment, which your topups already show.

Thanks,
Alex
