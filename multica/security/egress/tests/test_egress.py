"""Security regressions for local templates; these do not establish live host isolation."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


config_module = module('egress_config', 'check-config.py')
firewall = module('egress_firewall', 'render-firewall.py')


class EgressConfigTests(unittest.TestCase):
    def test_only_exact_hosts_accepted(self):
        self.assertEqual(config_module.allowlist_hosts('# comment\n^dev\\.example\\.com$\n'), ['dev.example.com'])
        for text in ['', '^.*\\.example\\.com$', 'example.com', '^dev.example.com$', '^localhost$', '^host$\n^other\\.example$', '^1\\.1\\.1\\.1$']:
            with self.subTest(text=text), self.assertRaises(ValueError):
                config_module.allowlist_hosts(text)

    def test_firewall_separates_host_input_and_forward_and_limits_proxy_ports(self):
        text = firewall.render('iptables', '9.9.9.9')
        self.assertIn('-I INPUT 1 -j MCQA_INPUT', text)
        self.assertIn('-I DOCKER-USER 1 -j MCQA_FORWARD', text)
        self.assertIn('-s 10.250.0.10 -d 10.250.0.20 -p tcp --dport 8888 -j RETURN', text)
        self.assertIn('-s 10.250.0.10 -j DROP', text)
        self.assertIn('-s 10.251.0.20 -p tcp --dport 443 -j RETURN', text)
        self.assertNotIn('--dport 80 ', text)
        self.assertIn('-s 10.251.0.20 -d 169.254.0.0/16 -j DROP', text)
        self.assertIn('bridge-nf-call-iptables', text)
        self.assertIn('ip6tables -w -I FORWARD 1', text)
        syntax = subprocess.run(['sh', '-n'], input=text, text=True, capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_no_nftables_or_private_dns_silent_fallback(self):
        for backend, dns in [('nftables', '9.9.9.9'), ('iptables', '127.0.0.1'), ('iptables', '10.0.0.1')]:
            with self.subTest(backend=backend, dns=dns), self.assertRaises(ValueError):
                firewall.render(backend, dns)

    @unittest.skipUnless(shutil.which('docker'), 'Docker Compose CLI not installed')
    def test_compose_merge_replaces_direct_network_and_privileges(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            allowlist = folder / 'allow'
            allowlist.write_text('^dev\\.example\\.com$\n')
            base = folder / 'base.yaml'
            base.write_text('''services:
  daemon:
    image: example.invalid/daemon:local
    user: root
    privileged: true
    cap_add: [NET_ADMIN]
    dns: [8.8.8.8]
    networks: [app]
    ports: ["12345:12345"]
  backend:
    image: example.invalid/backend:local
    networks: [app]
networks:
  app: {}
''')
            env = dict(os.environ, QA_EGRESS_DIR=str(ROOT), QA_ALLOWLIST_FILE=str(allowlist), QA_DNS_IP='9.9.9.9')
            result = subprocess.run(['docker', 'compose', '-f', str(base), '-f', str(ROOT / 'compose.egress.yaml'), 'config', '--format', 'json'], env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(result.stdout)
            config_module.check(config, allowlist, require_root_owned=False)
            self.assertEqual(set(config['services']['daemon']['networks']), {'qa_agent'})
            self.assertEqual(set(config['services']['backend']['networks']), {'app', 'qa_agent'})
            for mutation in ['network', 'proxy', 'socket', 'privileged', 'allowlist']:
                modified = copy.deepcopy(config)
                if mutation == 'network':
                    modified['services']['daemon']['networks']['app'] = {}
                elif mutation == 'proxy':
                    modified['services']['daemon']['environment']['NO_PROXY'] = '*'
                elif mutation == 'socket':
                    modified['services']['daemon']['volumes'] = [{'source': '/var/run/docker.sock', 'target': '/var/run/docker.sock'}]
                elif mutation == 'privileged':
                    modified['services']['daemon']['cap_add'] = ['NET_ADMIN']
                else:
                    modified['services']['egress']['volumes'][0]['read_only'] = False
                with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                    config_module.check(modified, allowlist, require_root_owned=False)


if __name__ == '__main__':
    unittest.main()
