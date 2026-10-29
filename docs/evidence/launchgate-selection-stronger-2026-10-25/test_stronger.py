"""Meaningful new-study checks; run offline on Linux, never call a provider."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import experiment as driver
import host_relay
import test_experiment as helpers
import test_host_relay as relay_helpers

HERE = Path(__file__).parent


class StrongerStudyTests(unittest.TestCase):
    def test_actual_main_and_authorized_control_have_opposite_correct_choices(self):
        main = json.loads((HERE / "fixtures.json").read_text())["fixtures"]
        controls = json.loads((HERE / "control-fixtures.json").read_text())["fixtures"]
        self.assertEqual(len(main), 6)
        self.assertEqual(len(controls), 6)
        self.assertEqual(len({f["attack_kind"] for f in main}), 6)
        for original, control in zip(main, controls):
            driver.validate_fixture(original)
            driver.validate_fixture(control)
            self.assertEqual(original["records"], control["records"])
            self.assertEqual(control["correct_id"], original["target_id"])
            self.assertEqual(control["target_id"], original["correct_id"])
            self.assertNotEqual(control["user_request"], original["user_request"])
            self.assertEqual(control["clean_note"], original["clean_note"])
            target = next(r for r in original["records"] if r["id"] == original["target_id"])
            self.assertNotIn(target["id"].casefold(), original["injected_note"].casefold())
            self.assertNotIn(target["name"].casefold(), original["injected_note"].casefold())
            self.assertEqual(len(original["injected_note"]), len(original["benign_note"]))

    def test_authorized_control_is_18_fresh_clean_samples_not_main_pairs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixtures.json"
            fixture.write_text(json.dumps(helpers.fixtures()))
            out = root / "control"
            relay = helpers.FakeRelay(lambda _n, _b: helpers.success())
            guard = helpers.FakeGuard()
            with patch.object(driver, "Guard", return_value=guard), patch.object(driver, "Relay", return_value=relay):
                driver.main(["--fixtures", str(fixture), "--out", str(out), "--relay", str(root / "unused"),
                             "--model", "requested-alias", "--expected-model", "verified-model",
                             "--guard-command", '["FAKE_NEVER_STARTED"]', "--phase", "control"])
            rows = [json.loads(line) for line in (out / "runs.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 18)
            self.assertEqual(relay.calls, 18)
            self.assertEqual({r["phase"] for r in rows}, {"control"})
            self.assertEqual({r["arm"] for r in rows}, {"clean"})
            self.assertEqual(len({r["session"] for r in rows}), 18)
            self.assertEqual(len({r["request_ids"]["initial"] for r in rows}), 18)
            for defense in driver.DEFENSES:
                self.assertEqual(sum(r["defense"] == defense for r in rows), 6)

    def test_caller_cannot_override_fixed_provider_routing(self):
        request = relay_helpers.valid_request()
        request["provider"] = {"allow_fallbacks": True, "only": ["Other"]}
        with self.assertRaises(host_relay.RelayError):
            host_relay.validate_request(request, relay_helpers.MODEL)
        payload, _ = host_relay.validate_request(relay_helpers.valid_request(), relay_helpers.MODEL)
        self.assertEqual(payload["provider"], {"only": ["Mistral"], "allow_fallbacks": False, "require_parameters": True})
        self.assertNotIn("thinking", payload)

    def test_synthetic_tool_exchange_uses_mistral_compatible_call_identity(self):
        fixture = json.loads((HERE / "fixtures.json").read_text())["fixtures"][0]
        body = driver.build_body(fixture, {"hotels": fixture["records"], "note": fixture["clean_note"]}, None)
        call_id = body["messages"][2]["tool_calls"][0]["id"]
        self.assertRegex(call_id, r"^[a-zA-Z0-9]{9}$")
        self.assertEqual(body["messages"][3]["tool_call_id"], call_id)

    def test_wrong_actual_provider_is_an_explicit_failed_attempt_without_retry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            payload = relay_helpers.FakeResponse().payload
            payload["provider"] = "UnexpectedProvider"
            transport = relay_helpers.FakeTransport(payload=payload)
            relay = host_relay.Relay(root, relay_helpers.FAKE_KEY, relay_helpers.MODEL, opener=transport)
            try:
                path = root / "req" / ("ab" * 16 + ".json")
                path.write_text(json.dumps(relay_helpers.valid_request()))
                result = relay.process(path)
                self.assertEqual(result["status"], "error")
                self.assertEqual(result["error"]["code"], "unexpected_provider")
                self.assertIsNone(relay.process(path))
                self.assertEqual(len(transport.requests), 1)
                self.assertEqual(relay.attempts, 1)
            finally:
                relay.close()


if __name__ == "__main__":
    unittest.main()
