"""Verify the already-mined CMC charge through the candidate without sending a transaction."""

import json

from aimarket_hub import settle, x402_bridge


tx = "0x24f175a2f0c56d9e1f3d3e0933a19d7964d057d22d761db0e468ec2cdc25c1d3"
payer = "0x1cdb27372ed3d5d37080a5a3256512b17ea321bc"
payee = "0x3c5f3a6ce224bb89d72f5eb4232ecc27f67b3eea"
offer = x402_bridge.Offer(x402_version=2, accept={}, resource=None, pay_to=payee, amount_atomic=10000,
                          max_timeout_s=30)
urls = settle.rpc_urls(8453)
receipt = settle.rpc_call(urls, "eth_getTransactionReceipt", [tx], chain_id=8453, timeout=5)
assert int(receipt["blockNumber"], 16) == 56863462
authorizations = [
    log["topics"][2] for log in receipt["logs"]
    if log["address"].lower() == x402_bridge.USDC.lower()
    and log["topics"][:2] == [settle.AUTHORIZATION_USED_TOPIC, "0x" + payer[2:].zfill(64)]
]
assert len(authorizations) == 1
nonce = authorizations[0]
assert x402_bridge._cmc_paid_on_base(tx, wallet=payer, nonce=nonce, offer=offer)
assert not x402_bridge._cmc_paid_on_base(tx, wallet=payer, nonce="0x" + "00" * 32, offer=offer)
finalized = settle.rpc_call(urls, "eth_getBlockByNumber", ["finalized", False], chain_id=8453, timeout=5)
print(json.dumps({"chain_id": 8453, "transaction_hash": tx, "receipt_block": 56863462,
                  "canonical_exact_payment": True, "different_nonce_rejected": True,
                  "payer": payer, "payee": payee, "amount_atomic": 10000,
                  "finalized_head": int(finalized["number"], 16)}, indent=2))
