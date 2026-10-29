"""Prospective five-profile schedule and direct version-effect contracts."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import experiment
import analyze
from test_experiment import fixtures, FakeRelay, FakeGuard, success
import test_analyze as helpers


class FiveProfileTests(unittest.TestCase):
    def test_five_profiles_route_to_the_correct_frozen_guard_and_control_once(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'fixtures.json';data.write_text(json.dumps(fixtures()))
            guards=[]
            def factory(command,errors):
                guard=FakeGuard(stop=command==['CANDIDATE'])
                guards.append((command,guard));return guard
            relay=FakeRelay(lambda n,body:success())
            with patch.object(experiment,'Guard',side_effect=factory),patch.object(experiment,'Relay',return_value=relay):
                experiment.main(['--fixtures',str(data),'--out',str(root/'out'),'--relay',str(root/'queue'),
                    '--model','requested','--expected-model','verified-model','--guard-command','["PUBLISHED"]',
                    '--candidate-guard-command','["CANDIDATE"]','--phase','control'])
            rows=[json.loads(line) for line in (root/'out/runs.jsonl').read_text().splitlines()]
            self.assertEqual(len(rows),30)
            self.assertEqual({r['defense'] for r in rows},set(experiment.FIVE_PROFILES))
            self.assertEqual(sum(r['continuation_calls'] for r in rows if r['defense']=='candidate_note_stop'),6)
            self.assertEqual(sum(r['continuation_calls'] for r in rows if r['defense']=='note_stop'),0)
            for command,guard in guards:
                self.assertEqual(sum(r['op']=='prepare' for r in guard.requests),12)
                self.assertTrue(guard.closed)

    def test_version_difference_in_differences_uses_each_versions_clean_baseline(self):
        rows=[]
        for fid in ('f1','f2'):
            for profile,selections in [('none',('A','T')),('note',('A','T')),('candidate_note',('T','T'))]:
                for arm,selected in zip(('clean','injected'),selections):
                    rows.append(helpers.row(arm,selected,identity=fid,defense=profile))
        report=analyze.analyze(helpers.document('f1','f2'),rows,helpers.plan(*rows),iterations=30)
        effect=next(x for x in report['version_comparison'] if x['guard']=='candidate_note' and x['baseline_arm']=='clean')
        self.assertEqual(effect['reference_defense'],'note')
        self.assertEqual(effect['point']['signed_attenuation'],1)
        self.assertEqual(effect['point']['common_unprotected_baseline_distance_reduction'],0)
        self.assertEqual(effect['point']['guard_clean_distribution_shift'],1)


if __name__=='__main__':unittest.main()
