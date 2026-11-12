"""Isolated crash/retry proof; ephemeral key, fake chain, no sockets or live funds."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "run_paid_cycle.py"
spec = importlib.util.spec_from_file_location("reviewed_paid_runner", SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.directory.chmod(0o700)
        self.account = runner.Account.create()
        (self.directory / ".aicom-pov-buyer.json").write_text(json.dumps({
            "private_key": self.account.key.hex()}))
        self.patches = [
            patch.object(runner, "PRIVATE", self.directory),
            patch.object(runner, "PAYER", self.account.address),
            patch.object(runner.Path, "home", return_value=self.directory),
            patch.object(socket, "getaddrinfo", side_effect=AssertionError("No DNS allowed")),
            patch.object(socket.socket, "connect", side_effect=AssertionError("No network allowed")),
        ]
        for item in self.patches:
            item.start()
        self.addCleanup(self.temp.cleanup)
        for item in reversed(self.patches):
            self.addCleanup(item.stop)
        self.r = object.__new__(runner.Runner)
        self.r.name = "factory"
        self.r.target = json.loads((SCRIPT.parent / "targets.json").read_text())["factory"]
        self.r.base = self.r.target["base"]
        self.r.journal_path = self.directory / "factory.json"
        self.r.summary = {}
        self.r.chain_clock = lambda: (1000, 1000, {})
        self.r.object_verified = lambda document: True
        self.r.balance = lambda who: 100000
        self.r.call = lambda to, data: "0x0"
        self.sent = []
        self.estimates = []
        self.crash = False

        def rpc(method, params):
            if method == "eth_estimateGas":
                self.estimates.append(params)
                return hex(100000)
            if method == "eth_gasPrice":
                return hex(1000000)
            if method == "eth_getTransactionCount":
                return hex(7)
            if method == "eth_getBalance":
                return hex(10**18)
            if method == "eth_sendRawTransaction":
                durable = json.loads(self.r.journal_path.read_text())
                self.assertEqual(durable["phase"], "broadcast_attempted")
                self.assertEqual(durable["signed_transaction"], params[0])
                self.assertEqual("0x" + runner.keccak(bytes.fromhex(params[0][2:])).hex(),
                                 durable["transaction_hash"])
                self.sent.append(durable["transaction_hash"])
                if self.crash:
                    raise TimeoutError("Fake RPC accepted, reply lost")
                return durable["transaction_hash"]
            raise AssertionError("Unexpected RPC " + method)

        self.r.rpc = rpc
        terms = dict(chain_id=8453, decimals=6, token_contract=runner.TOKEN,
                     pay_to=self.r.target["payee"], amount_units=2000, amount_usd=.002,
                     fee_units=0, eip712_name="USD Coin", eip712_version="2",
                     min_confirmations=3)
        offer = dict(protocol="SELLER-OP/1", operation_id="op_" + "a" * 32,
                     product_id=self.r.target["product_id"],
                     capability_id=self.r.target["capability_id"],
                     wallet=self.account.address, terms=terms, input_schema={},
                     invoice=dict(nonce="0x" + "b" * 64, expires_at=1300), expires_at=1300)
        self.state = dict(phase="prepared", target="factory", prepared={"offer": offer,
                           "operation_token": "fake-only-local-token"}, input=self.r.target["input"],
                           input_sha256=runner.digest(self.r.target["input"]),
                           summary_before={"principal_atomic": 2000})
        runner.exclusive_private_checkpoint(self.r.journal_path, self.state)

    def test_one_send_has_durable_hash_and_attempt_before_broadcast(self):
        self.r.sign_and_send(self.state, 7)
        self.assertEqual(len(self.sent), 1)
        saved = json.loads(self.r.journal_path.read_text())
        self.assertEqual(saved["phase"], "broadcast_returned")
        self.assertEqual(saved["transaction_hash"], self.sent[0])

    def test_uncertain_broadcast_resume_does_not_sign_or_send_again(self):
        self.crash = True
        with self.assertRaises(TimeoutError):
            self.r.sign_and_send(self.state, 7)
        saved = json.loads(self.r.journal_path.read_text())
        self.assertEqual(saved["phase"], "broadcast_attempted")
        self.assertEqual(len(self.sent), 1)
        reads = []

        def unconfirmed(method, params):
            reads.append((method, params))
            self.assertEqual(method, "eth_getTransactionReceipt")
            raise runner.Stop("Fake confirmation unavailable; resume same hash")

        self.r.rpc = unconfirmed
        with patch.object(runner.Account, "from_key", side_effect=AssertionError("No key on resume")):
            with self.assertRaises(runner.Stop):
                self.r.confirm_and_execute(saved)
        self.assertEqual(reads, [("eth_getTransactionReceipt", [self.sent[0]])])
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(json.loads(self.r.journal_path.read_text())["transaction_hash"], self.sent[0])

    def test_aggregate_principal_cap_stops_before_any_send(self):
        previous = {"signed_transaction": "fake", "summary_before": {"principal_atomic": 12000},
                    "fee_bound_wei": "1"}
        (self.directory / "earlier.json").write_text(json.dumps(previous))
        with self.assertRaises(runner.Stop):
            self.r.sign_and_send(self.state, 7)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.estimates, [], "No spendable authorization goes to RPC outside budget")
        self.assertEqual(json.loads(self.r.journal_path.read_text())["phase"], "prepared")

    def test_authorization_only_prior_attempt_counts_before_key_or_signature(self):
        previous = {"authorization_signature": "fake-local-only", "phase": "authorization_signed",
                    "summary_before": {"principal_atomic": 12000}, "fee_bound_wei": "1"}
        (self.directory / "earlier.json").write_text(json.dumps(previous))
        with patch.object(runner.Account, "from_key", side_effect=AssertionError("No key outside budget")):
            with self.assertRaises(runner.Stop):
                self.r.sign_and_send(self.state, 7)
        self.assertEqual(self.sent, [])
        self.assertEqual(self.estimates, [])
        self.assertEqual(json.loads(self.r.journal_path.read_text())["phase"], "prepared")

    def test_expired_before_send_retains_signed_hash_without_broadcast(self):
        self.r.chain_clock = unittest.mock.Mock(side_effect=[(1000, 1000, {}),
                                                             (1000, 1000, {}),
                                                             (1200, 1200, {})])
        with self.assertRaises(runner.Stop):
            self.r.sign_and_send(self.state, 7)
        saved = json.loads(self.r.journal_path.read_text())
        self.assertEqual(self.sent, [])
        self.assertEqual(saved["phase"], "signed")
        self.assertEqual("0x" + runner.keccak(bytes.fromhex(saved["signed_transaction"][2:])).hex(),
                         saved["transaction_hash"])

    def test_changed_pending_nonce_stops_before_signing_or_send(self):
        with self.assertRaises(runner.Stop):
            self.r.sign_and_send(self.state, 8)
        self.assertEqual(self.sent, [])
        saved = json.loads(self.r.journal_path.read_text())
        self.assertFalse(saved.get("signed_transaction"))
        self.assertIn(saved["phase"], ("prepared", "authorization_signed"))


if __name__ == "__main__":
    unittest.main()
