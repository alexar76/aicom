import importlib.util
import json
import http.client
import socket
import ssl
import subprocess
import time
from pathlib import Path
import threading
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('qa_broker', Path(__file__).resolve().parents[1] / 'broker.py')
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


def report():
    return {'job': broker.JOB, 'checks': [{'name': name, 'pass': True, 'status': 200} for name in broker.LABELS], 'passed': True}


class BrokerTests(unittest.TestCase):
    def test_fixed_command_has_no_caller_fields_or_host_credentials(self):
        command = broker.worker_command()
        self.assertIn('qa-worker', command)
        self.assertIn('env', command)
        self.assertIn('-i', command)
        self.assertEqual(command[-4:], ['npm', '--silent', 'run', 'smoke'])
        self.assertNotIn('sh', command)
        self.assertFalse(any('TOKEN=' in value or 'API_KEY=' in value for value in command))

    def test_public_report_preserves_only_fixed_structured_fields(self):
        good = broker.public_report(json.dumps(report()).encode(), 0)
        self.assertTrue(good['passed'])
        for transform in [lambda r: r.update(output='ghp_' + 'a' * 40),
                          lambda r: r['checks'][0].update(name='attacker supplied prose'),
                          lambda r: r['checks'][0].update(status='200'),
                          lambda r: r['checks'][0].update(status=True),
                          lambda r: r['checks'][0].update(status=503),
                          lambda r: r.update(passed=False)]:
            raw = report()
            transform(raw)
            with self.assertRaises(ValueError):
                broker.public_report(json.dumps(raw).encode(), 0)
        with self.assertRaises(ValueError):
            broker.public_report(b'x' * (broker.MAX_OUTPUT + 1), 0)

    def test_rate_and_concurrent_boundaries(self):
        now = [0]
        controller = broker.Controller(lambda: (0, json.dumps(report()).encode()), lambda: now[0])
        for _ in range(3):
            self.assertEqual(controller.run()[0], 200)
        self.assertEqual(controller.run()[0], 429)
        now[0] = 300
        self.assertEqual(controller.run()[0], 200)
        controller.lock.acquire()
        try:
            self.assertEqual(controller.run()[0], 409)
        finally:
            controller.lock.release()

    def test_invalid_worker_output_is_never_echoed(self):
        token = 'ghp_' + 'a' * 40
        controller = broker.Controller(lambda: (1, token.encode()))
        status, body = controller.run()
        self.assertEqual(status, 502)
        self.assertNotIn(token, json.dumps(body))

    def test_host_quota_persists_across_controller_restarts_and_rejects_clock_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            path.chmod(0o700)
            clock = [100000]
            for _ in range(10):
                self.assertTrue(broker.Quota(path, lambda: clock[0]).reserve())
            self.assertFalse(broker.Quota(path, lambda: clock[0]).reserve())
            clock[0] += 12 * 3600
            self.assertTrue(broker.Quota(path, lambda: clock[0]).reserve())
            clock[0] -= 12 * 3600
            with self.assertRaises(ValueError):
                broker.Quota(path, lambda: clock[0]).reserve()

    def test_http_interface_has_only_empty_fixed_job_requests(self):
        calls = []
        def run():
            calls.append(True)
            return 0, json.dumps(report()).encode()
        server = broker.Server(('127.0.0.1', 0), broker.handler(broker.Controller(run), {'127.0.0.1'}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for path, body, expected in [('/run/platform-smoke?url=example.invalid', None, 404),
                                         ('/run/arbitrary-command', None, 404),
                                         ('/run/platform-smoke', '{"command":"env"}', 400),
                                         ('/run/platform-smoke', None, 200)]:
                connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
                connection.request('POST', path, body=body)
                response = connection.getresponse()
                self.assertEqual(response.status, expected)
                response.read()
                connection.close()
            self.assertEqual(len(calls), 1)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_tls_handshake_is_bounded_in_a_thread_and_does_not_block_a_valid_client(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                            '-subj', '/CN=QA local TLS fixture', '-keyout', str(root / 'key.pem'),
                            '-out', str(root / 'cert.pem')], check=True, capture_output=True)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(root / 'cert.pem', root / 'key.pem')
            calls = []
            def run():
                calls.append(True)
                return 0, json.dumps(report()).encode()
            server = broker.Server(('127.0.0.1', 0), broker.handler(broker.Controller(run), {'127.0.0.1'}),
                                   tls_context=context, handshake_timeout=0.3)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            slow = socket.create_connection(('127.0.0.1', server.server_port), timeout=1)
            try:
                # The raw connection sends no ClientHello. A concurrent legitimate TLS client must still run.
                client = http.client.HTTPSConnection('127.0.0.1', server.server_port,
                                                    context=ssl._create_unverified_context(), timeout=1)
                client.request('POST', '/run/platform-smoke')
                response = client.getresponse()
                self.assertEqual(response.status, 200)
                response.read(); client.close()
                slow.settimeout(1)
                self.assertEqual(slow.recv(1), b'')
                self.assertEqual(len(calls), 1)
            finally:
                slow.close(); server.shutdown(); server.server_close(); thread.join(timeout=2)


if __name__ == '__main__':
    unittest.main()
