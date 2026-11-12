# Draft only — not sent

Subject: `settlement_self_funded` also covers router purchases/refunds and closes the unproven lane

On 9 November, modelmarket.dev's eight paid routes have `settlement_self_funded`, detail `below the settlement floor`, and `executeViaCallableNow: false` in the public index and route results. We are not claiming the underlying net count clears the proven floor, or asking that our own purchases count as independent demand.

There appears to be a narrower classification issue in pinned source [81a674d1](https://github.com/MikeyPetrillo/Agent402/tree/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7):

- [evidence-binding.js#L220-L245](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/evidence-binding.js#L220-L245) deducts router-owned purchases and refunds as well as seller-funded calls. [Line 272](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/evidence-binding.js#L272) puts any reduced Bazaar gross figure in `selfByWallet`.
- [dispatch-eligibility.js#L312](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/dispatch-eligibility.js#L312) labels that held figure `settlement_self_funded` if it would clear the floor. [Line 332](https://github.com/MikeyPetrillo/Agent402/blob/81a674d1a3cf7fdbbcc04f4da366c144ccd393f7/src/dispatch-eligibility.js#L332) then excludes it from the unproven lane.

A reduced synthetic case, not our measured counts: one wallet/origin has 50 Bazaar calls from four payers, one call from the router, zero seller-funded calls and zero refunds; after excluding the router it has 49 calls/three payers. Its net evidence correctly fails the default proven floor. However, the gross figure enters selfByWallet and passes 50/3, so its label is `settlement_self_funded` and a $0.001 route loses the unproven lane. The same 49 independent calls with a gross count of 49 stay in the unproven lane. The reason's public description of money the seller first sent a payer is not true for this case.

Could the net/gross evidence for modelmarket.dev at `0x1218ff36c5d2e3b6a565cdb1a8b1accfc606ad0a` be checked, with the deduction classes separated: actual funded calls, refunds, router purchases and any retained circular/read-pending status? The free index does not reveal those figures, so we cannot attribute the current label to one of them. We are not requesting payer identities.

For a correction, keeping the proven threshold while reporting the actual deduction class would avoid the unsupported label. The decision to allow the bounded unproven lane for router-purchase/refund-only deductions can then be made explicitly, independently of the display reason. Actual self-funded evidence can retain its current block.

Disclosure: our 30 October WARDEN purchase through Agent402 was an operator-funded test. The payout wallet paid the router $0.01 and received $0.001 for WARDEN. It should not be counted as independent demand. The two USDC events occurred in the same block, with the upstream payment first (global log 73), followed by the router charge (global log 342), which may matter to the refund/pool accounting. We have not established how that test appears in your retained state.

Prepared with AI assistance. No message or issue has been sent.
