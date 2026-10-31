"""Offline Ed25519, on-chain Transfer and AuthorizationUsed checks for saved evidence."""
from pathlib import Path
from copy import deepcopy
from decimal import Decimal
import json,os
from eth_utils import keccak
from aimarket_agent.receipts import verify_receipt
BASE=Path(__file__).resolve().parent
order=os.getenv('AICOM_PAYMENT_ORDER','original')
if order not in ('original','a2a-fixed','mcp-paid'):raise SystemExit('Unknown order')
R=BASE if order=='original' else BASE/order
load=lambda n:json.loads((R/n).read_text())
receipt=load('paid-receipt.json');provider=json.loads((BASE/'provider-well-known.json').read_text())['body']['signer_public_key'];hub=json.loads((BASE/'hub-well-known.json').read_text())['body']['signer_public_key']
checks={'provider_key_matches_receipt':receipt['signature']['public_key']==provider,'provider_ed25519_valid':bool(verify_receipt(receipt,provider)),'hub_key_rejected':not bool(verify_receipt(receipt,hub))}
tampered=deepcopy(receipt);tampered['price_usd']=0
checks['tampered_price_rejected']=not bool(verify_receipt(tampered,provider))
j=load('payment-journal.json');chain=load('chain-transaction-receipt.json');tx=load('chain-transaction.json')
checks['chain_transaction_succeeded']=int(chain['status'],16)==1
checks['correct_chain']=int(tx['chainId'],16)==8453
checks['correct_transaction_sender']=tx['from'].lower()==j['payer'].lower()
checks['correct_token_contract']=tx['to'].lower()==j['asset'].lower()
transfer='0x'+keccak(text='Transfer(address,address,uint256)').hex()
authorization='0x'+keccak(text='AuthorizationUsed(address,bytes32)').hex()
checks['exact_usdc_transfer_event']=any(x['address'].lower()==j['asset'].lower() and x['topics'][0].lower()==transfer and '0x'+x['topics'][1][-40:].lower()==j['payer'].lower() and '0x'+x['topics'][2][-40:].lower()==j['payee'].lower() and int(x['data'],16)==int(j['amount_atomic']) for x in chain['logs'])
checks['invoice_nonce_used_on_chain']=any(x['address'].lower()==j['asset'].lower() and x['topics'][0].lower()==authorization and x['topics'][2].lower()==j['authorization_nonce'].lower() for x in chain['logs'])
fee=int(chain['gasUsed'],16)*int(chain['effectiveGasPrice'],16)+int(chain.get('l1Fee','0x0'),16)
budget=load('payment-budget.json');rate=Decimal(budget['native_price']['observations'][0]['price_usd'])
cost={'service_usdc':str(Decimal(j['amount_atomic'])/10**6),'network_fee_eth':str(Decimal(fee)/10**18),'eth_usd_recorded':str(rate),'total_usd_at_recorded_rate':str(Decimal(j['amount_atomic'])/10**6+Decimal(fee)/10**18*rate)}
assert all(checks.values()),checks
(R/'independent-verification.json').write_text(json.dumps({'checks':checks,'cost':cost,'signature_scope':'Ed25519 invoke receipt; no independent ML-DSA verification; v1 receipt does not cryptographically bind weather payload or payment transaction'},indent=2)+'\n')
print(json.dumps({'checks':checks,'cost':cost},indent=2))
