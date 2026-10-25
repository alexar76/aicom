"""Ensure incomplete or inconsistent supplier evidence cannot pass reconciliation."""
import copy
import json
from pathlib import Path
import unittest

from verify_supplier_statement import reconcile

HERE = Path(__file__).resolve().parent


class SupplierStatementTests(unittest.TestCase):
    def setUp(self):
        self.observation = json.loads((HERE / 'supplier-billing-observation.json').read_text())
        self.production = json.loads((HERE / 'production-evidence.json').read_text())

    def rejects(self):
        with self.assertRaises(AssertionError):
            reconcile(self.observation, self.production)

    def test_actual_statement_reconciles(self):
        result = reconcile(self.observation, self.production)
        self.assertTrue(result['net_supplier_loss_verified'])
        self.assertEqual(result['net_supplier_delta_usd'], '0.00')

    def test_missing_refund_rejected(self):
        self.observation['visible_latest_transactions'].pop(0)
        self.rejects()

    def test_duplicate_debit_rejected(self):
        self.observation['visible_latest_transactions'].append(copy.deepcopy(self.observation['visible_latest_transactions'][1]))
        self.rejects()

    def test_refund_shortfall_rejected(self):
        self.observation['visible_latest_transactions'][0]['amount'] = '+0.29'
        self.rejects()

    def test_other_order_rejected(self):
        self.observation['visible_latest_transactions'][1]['transaction_id'] = 'other-order'
        self.rejects()

    def test_unrestored_balance_rejected(self):
        self.observation['current_balance'] = '19.99'
        self.rejects()


if __name__ == '__main__':
    unittest.main()
