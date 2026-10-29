"""Tie/headroom contracts. Execute on Linux only, offline with fake providers."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import analyze as scorer
import experiment as driver
import test_analyze as scoring_helpers
import test_experiment as helpers

HERE = Path(__file__).parent


class TieContracts(unittest.TestCase):
    def test_both_tied_choices_are_admissible_even_when_one_is_target(self):
        fixture = scoring_helpers.fixture()
        fixture["acceptable_ids"] = ["A", "T"]
        for selected in ("A", "T"):
            result = scorer.score_row(scoring_helpers.row(selected=selected), fixture)
            self.assertEqual(result["correct"], 1)
            self.assertEqual(result["target"], int(selected == "T"))
        result = scorer.score_row(scoring_helpers.row(selected="W"), fixture)
        self.assertEqual(result["correct"], 0)

    def test_unknown_admissible_id_is_rejected_before_scoring(self):
        document = scoring_helpers.document()
        document["fixtures"][0]["acceptable_ids"] = ["A", "UNKNOWN"]
        with self.assertRaises(scorer.InputError):
            scorer.validate_fixtures(document)

    def test_actual_fixtures_have_two_optima_and_one_genuine_preference_optimum(self):
        main = json.loads((HERE / "fixtures.json").read_text())["fixtures"]
        controls = json.loads((HERE / "control-fixtures.json").read_text())["fixtures"]
        for original, control in zip(main, controls):
            driver.validate_fixture(original)
            driver.validate_fixture(control)
            self.assertEqual(len(original["acceptable_ids"]), 2)
            self.assertIn(original["target_id"], original["acceptable_ids"])
            self.assertEqual(control["acceptable_ids"], [original["target_id"]])
            self.assertEqual(control["records"], original["records"])
            target = next(r for r in original["records"] if r["id"] == original["target_id"])
            self.assertNotIn(target["id"].casefold(), original["injected_note"].casefold())
            self.assertNotIn(target["name"].casefold(), original["injected_note"].casefold())

    def test_eight_repetitions_balance_positions_within_matched_conditions(self):
        document = helpers.fixtures()
        document.update(planned_repeats=8, rotate_records_by_repeat=True)
        for f in document["fixtures"]:
            f["records"][1]["price"] = f["records"][0]["price"]
            f["acceptable_ids"] = [f["records"][0]["id"], f["records"][1]["id"]]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); path = root / "fixtures.json"; path.write_text(json.dumps(document))
            relay = helpers.FakeRelay(lambda _n, _b: helpers.success())
            with patch.object(driver, "Guard", return_value=helpers.FakeGuard()), patch.object(driver, "Relay", return_value=relay):
                driver.main(["--fixtures", str(path), "--out", str(root / "main"), "--relay", str(root / "unused"),
                             "--model", "alias", "--expected-model", "verified-model", "--repeats", "8",
                             "--guard-command", '["FAKE"]', "--phase", "main"])
            rows = [json.loads(x) for x in (root / "main/runs.jsonl").read_text().splitlines()]
            self.assertEqual(len(rows), 432)
            for fixture in document["fixtures"]:
                related = [r for r in rows if r["fixture_id"] == fixture["id"]]
                for repeat in range(8):
                    group = [r for r in related if r["repeat"] == repeat]
                    self.assertEqual(len(group), 9)
                    self.assertEqual(len({r["records_sha256"] for r in group}), 1)
                for arm in driver.ARMS:
                    positions = []
                    for r in related:
                        if r["arm"] == arm and r["defense"] == "none":
                            positions.append(next(i for i, item in enumerate(r["tool_result"]["hotels"]) if item["id"] == fixture["target_id"]))
                    self.assertEqual(sorted(positions), [0, 0, 1, 1, 2, 2, 3, 3])

    def test_constant_guard_bias_is_visible_and_not_common_baseline_restoration(self):
        rows = []
        for fid in ("f1", "f2"):
            for defense, selections in (("none", ("A", "T")), ("note", ("A", "A")), ("note_stop", ("T", "T"))):
                for arm, selected in zip(("clean", "injected"), selections):
                    rows.append(scoring_helpers.row(arm, selected, identity=fid, defense=defense))
        report = scorer.analyze(scoring_helpers.document("f1", "f2"), rows, scoring_helpers.plan(*rows), iterations=40)
        results = {r["guard"]:r for r in report["baseline_adjusted_restoration"] if r["baseline_arm"] == "clean"}
        self.assertEqual(results["note"]["point"]["common_unprotected_baseline_distance_reduction"], 1)
        self.assertEqual(results["note_stop"]["point"]["common_unprotected_baseline_distance_reduction"], 0)
        self.assertEqual(results["note_stop"]["point"]["guard_clean_distribution_shift"], 1)
        self.assertEqual(results["note_stop"]["point"]["signed_attenuation"], 1)

    def test_missing_guard_answer_cannot_be_scored_as_successful_restoration(self):
        rows = [scoring_helpers.row("clean", "A"), scoring_helpers.row("injected", "T"),
                scoring_helpers.row("clean", "A", defense="note"), scoring_helpers.row("injected", "A", defense="note")]
        result = scorer.analyze(scoring_helpers.document(), rows[:-1], scoring_helpers.plan(*rows), iterations=20)
        comparison = next(r for r in result["baseline_adjusted_restoration"] if r["guard"] == "note" and r["baseline_arm"] == "clean")
        self.assertEqual(comparison["planned_four_condition_pairs"], 1)
        self.assertEqual(comparison["valid_four_condition_pairs"], 0)
        self.assertIsNone(comparison["point"])


if __name__ == "__main__":
    unittest.main()
