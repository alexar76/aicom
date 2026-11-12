# Live read-only checks 2026-11-11 (owner approved UNI DB read)

Alerter (skopos-vps, 72h): only disk alerts open (oracle/admin-vps ~3 days; attested/pingblip flapping). No sweep/canary alerts.

Base mainnet (publicnode, block 55949344): EscrowV2 0xa4cb, V1 0x12Db, 0x0606, 0x3Df8, lotteries 0x291b/0xbda3,
x402 bridge wallet 0xdE46 — all 0 USDC / 0 ETH. HORKOS hot 0xBE0b: 0.05 USDC + 0.00198 ETH. Owner 0x1218: 3.5855 USDC.

Public /ai-market/v2/stats/live: outstanding_obligations 0 on apex, lab, hunt, indep, attested.
UNI: 847 obligations $115,656.84; operator_net_usd -114.184; expired_volume 2867.78.

UNI hub DB (factory-vps, modelmarket-hub-uni, sqlite mode=ro):
- channel_payout_obligations: 847 owed, 11,565,684 cents. 846 expiry_remainder from ONE wallet 0x3c44cddd (anvil acct #2,
  realm buyer), 1 close_remainder (0x90F79bf6). Peak 09-28..10-02 (~777 rows): buyer opened ~$170 channels and let them
  expire after using cents. amount==balance for all 847; no orphans; none escrow-funded. Documented design (money-rails §3:
  refund_executed_usd = 0, no broadcast), but liability only grows; nothing ever pays these.
- channels: 864 expired, 164 settled, 1 open (ch_baf3bcf96, 39.21 of 116.94 left, expires 11-11 18:31Z). Conservation
  original = balance + used holds for all rows; no negatives; no duplicate deposit tx hashes.
- 161 settled escrow-funded probe channels (0x90F79bf6, $1 each, 1 cent used) keep 99c balance; settle_tx_hash empty,
  no obligation (escrow path by design: contract returns the remainder at settleChannel). Whether settleChannel is ever
  called on the anvil escrow for these is not verified (HORKOS signs only debitChannel; settle manual).
- 8 expired escrow channels from 08-29 with $15.94 balance, no obligation (escrow path, pre-feature). OK by design.
- channel_holds: captured 324,002 / released 32,459, none 'held'. hub.db credit_holds: captured 156, released 65, none held.
  mandate_holds empty. x402_payments 3 settled.
- escrow_bridge.db debit_authorizations: 163 confirmed, 1 abandoned (0x9d1318c9, $0.01, 10-03, "deadline passed before
  submission", 7 attempts), 2 PENDING since 2026-08-28 (0xb8f1ea66, 0xca313e0c, $0.02 each, deadline 2026-08-28 15:03Z,
  attempts 0) on OLD escrow 0xf4fe699c which has NO CODE on the UNI anvil now (0 bytes; current 0xe7f1725e = 8108 bytes).
  Trace: mirror._preflight Guard 0 -> chain.receipt_already_used -> eth_call returns "0x" -> _decode_words raises
  ChainUnavailable -> OUTCOME_BLOCKED, return False BEFORE the deadline guard (mirror.py:244) -> row can never be
  abandoned; stays pending forever. Collector on: AIMARKET_ESCROW_COLLECT_INTERVAL_S=300, bridge enabled.
