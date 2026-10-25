"""Reconcile the observed supplier Billing rows against the production order."""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def reconcile(observation, production):
    order = production['order']
    rows = observation['visible_latest_transactions']
    assert observation['currency'] == 'USD'
    assert observation['no_intervening_or_later_transaction']
    assert len(rows) == 2
    refund, purchase = rows
    amount = Decimal(str(order['costUsd']))
    assert amount == Decimal('0.30')
    assert purchase['transaction_id'] == order['orderRef']
    assert refund['transaction_id'] == order['profileId']
    assert purchase['activity'] == 'Base Plan Purchase' and purchase['transaction_type'] == 'Outgoing'
    assert refund['activity'] == 'Base Plan Refund' and refund['transaction_type'] == 'Incoming'
    debit, credit = Decimal(purchase['amount']), Decimal(refund['amount'])
    assert debit == -amount and credit == amount and debit + credit == 0
    before = Decimal(observation['preceding_transaction']['balance_after'])
    assert before + debit == Decimal(purchase['balance_after'])
    assert Decimal(purchase['balance_after']) + credit == Decimal(refund['balance_after'])
    assert before == Decimal(refund['balance_after']) == Decimal(observation['current_balance'])
    assert Decimal(str(production['supplier_balance_usd'])) == before
    assert production['order']['released'] is True
    assert len(production['profiles']) == 1 and production['profiles'][0]['state'] == 'CANCEL'
    assert production['profiles'][0]['profileId'] == refund['transaction_id']
    return {'supplier': 'eSIM Access', 'order_no': order['orderRef'], 'profile_id': order['profileId'],
            'wholesale_amount_usd': str(amount), 'debit_statement_verified': True,
            'credit_statement_verified': True, 'net_supplier_loss_verified': True,
            'net_supplier_delta_usd': str(debit + credit), 'balance_before_usd': str(before),
            'balance_after_purchase_usd': purchase['balance_after'],
            'balance_after_refund_usd': refund['balance_after'],
            'no_extra_supplier_charge_in_cycle': True, 'status': 'verified',
            'source': observation['source'], 'source_url': observation['source_url'],
            'observation_file': 'supplier-billing-observation.json', 'new_supplier_mutations': 0}


def main():
    observation = json.loads((HERE / 'supplier-billing-observation.json').read_text())
    production = json.loads((HERE / 'production-evidence.json').read_text())
    result = reconcile(observation, production)
    result['checked_at_utc'] = datetime.now(timezone.utc).isoformat()
    (HERE / 'supplier-statement-verification.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
