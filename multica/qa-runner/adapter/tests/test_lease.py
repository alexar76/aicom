import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('lease', ROOT / 'renew-lease.py')
lease = importlib.util.module_from_spec(spec); spec.loader.exec_module(lease)

class LeaseTests(unittest.TestCase):
    def test_fixed_request_and_deterministic_12h_budget(self):
        start = 1800000000 // lease.WINDOW * lease.WINDOW
        first = lease.lease(start)
        self.assertEqual(first, lease.lease(start + lease.WINDOW - 1))
        self.assertNotEqual(first['taskId'], lease.lease(start + lease.WINDOW)['taskId'])
        self.assertEqual(first['operations'], [{'id':'platform_smoke','title':'Run the fixed secretless platform smoke check','maxUses':10,'request':{'method':'POST','url':'https://10.250.0.1:8443/run/platform-smoke','headers':{'accept':'application/json'}}}])
        expiry = lease.datetime.fromisoformat(first['expiresAt'].replace('Z','+00:00')).timestamp()
        self.assertEqual(expiry-start, 23*3600)
        self.assertEqual(first['resources'], [])

    def test_policy_merge_preserves_every_other_setting(self):
        original = {'mode':'ask','labels':{'custom':['private']},'allowedDestinations':['example.invalid'],'answerNote':'instruction','future_setting':{'kept':True}}
        merged = lease.policy_for(original, b'manifest')
        self.assertEqual({k:v for k,v in merged.items() if k!='taskAdapter'}, original)
        self.assertEqual(merged['taskAdapter'], {'mode':'capabilities','server':'qa_runner','manifestSha256':hashlib.sha256(b'manifest').hexdigest()})
        for mode in ['deny','audit','off']:
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                lease.policy_for({'mode':mode}, b'manifest')
        for section in [{'server':'other','mode':'capabilities'}, {'server':'qa_runner','mode':'strict','manifestSha256':'0'*64}]:
            with self.assertRaises(ValueError): lease.policy_for({'taskAdapter':section}, b'manifest')

    def test_renewal_never_resets_usage_or_session_state_and_refuses_clock_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            state=root/'state'; state.mkdir(mode=0o700)
            private=root/'private'; private.mkdir(mode=0o700)
            policy=root/'policy.json'; policy.write_text('{"mode":"ask","answerNote":"instruction"}'); policy.chmod(0o600)
            sentinel=state/'retained-sensitive-session.json'; sentinel.write_bytes(b'unchanged synthetic session marker')
            usage=state/'tasks'; usage.mkdir(); (usage/'previous-window.json').write_bytes(b'unchanged synthetic spent-budget marker')
            now=1800000000 // lease.WINDOW * lease.WINDOW + 1
            first=lease.renew(state,policy,private,now,True,os.getuid())
            manifest=(state/'task-manifest.json').read_bytes()
            second=lease.renew(state,policy,private,now+60,True,os.getuid())
            self.assertEqual(first['manifestSha256'], second['manifestSha256'])
            self.assertEqual((state/'task-manifest.json').read_bytes(), manifest)
            self.assertEqual(sentinel.read_bytes(), b'unchanged synthetic session marker')
            self.assertEqual((usage/'previous-window.json').read_bytes(), b'unchanged synthetic spent-budget marker')
            self.assertEqual(json.loads(policy.read_text())['answerNote'], 'instruction')
            self.assertEqual((state/'task-manifest.json').stat().st_mode & 0o777, 0o444)
            self.assertEqual(policy.stat().st_mode & 0o777, 0o644)
            with self.assertRaises(ValueError): lease.renew(state,policy,private,now-lease.WINDOW,True,os.getuid())
            self.assertEqual((state/'task-manifest.json').read_bytes(), manifest)

    def test_privileged_atomic_write_rejects_symlink_ancestors(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory).resolve(); actual=root/'actual'; actual.mkdir(); (root/'link').symlink_to(actual, target_is_directory=True)
            with self.assertRaises(OSError): lease.atomic(root/'link'/'manifest.json',b'blocked',0o444)
            self.assertFalse((actual/'manifest.json').exists())

    def test_global_server_is_disabled_and_only_private_fragment_enables_env_i(self):
        allowed={'PATH','HOME','WARDEN_STATE_DIR','WARDEN_FLOW_POLICY','NODE_EXTRA_CA_CERTS'}
        for name, enabled in [('global-disabled.json',False),('private-qa-profile.json',True)]:
            config=json.loads((ROOT/'fragments'/name).read_text())
            server=config['mcp']['qa_runner']; command=server['command']
            self.assertEqual(server['enabled'],enabled)
            self.assertEqual(config['tools']['qa_runner_*'],enabled)
            self.assertEqual(command[:2],['/usr/bin/env','-i'])
            assignments=[value for value in command[2:] if '=' in value]
            self.assertEqual({value.split('=',1)[0] for value in assignments},allowed)
            self.assertEqual(command[-2:],['/opt/opencode-guard/qa-adapter/warden/dist/mcp-server.js','task'])

if __name__=='__main__': unittest.main()
