#!/usr/bin/env python3
"""Host-only TLS controller for one fixed, credential-free QA container job."""
from __future__ import annotations

import argparse
from collections import deque
import json
import os
from pathlib import Path
import selectors
import sqlite3
import ssl
import stat
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

JOB = 'platform_smoke'
LABELS = ('backend_health', 'modelmarket_https', 'hub_https')
MAX_OUTPUT = 65_536


class Quota:
    """A root-side budget survives MCP state deletion and controller restarts."""
    def __init__(self, directory: Path, clock=time.time):
        info = directory.lstat()
        if directory.is_symlink() or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('unsafe_quota_directory')
        self.path = directory / 'quota.sqlite3'
        if self.path.is_symlink():
            raise ValueError('unsafe_quota_file')
        self.clock = clock
        with sqlite3.connect(self.path, timeout=1) as connection:
            connection.execute('CREATE TABLE IF NOT EXISTS quota (window INTEGER PRIMARY KEY, used INTEGER NOT NULL)')
        self.path.chmod(0o600)

    def reserve(self) -> bool:
        window = int(self.clock()) // (12 * 3600)
        with sqlite3.connect(self.path, timeout=1, isolation_level=None) as connection:
            connection.execute('BEGIN IMMEDIATE')
            latest = connection.execute('SELECT max(window) FROM quota').fetchone()[0]
            if latest is not None and latest > window:
                raise ValueError('quota_clock_rollback')
            row = connection.execute('SELECT used FROM quota WHERE window=?', (window,)).fetchone()
            if row and row[0] >= 10:
                return False
            connection.execute('INSERT INTO quota VALUES (?,1) ON CONFLICT(window) DO UPDATE SET used=used+1', (window,))
            connection.execute('DELETE FROM quota WHERE window < ?', (window - 1,))
            connection.commit()
            return True


def worker_command() -> list[str]:
    # No request values, host secrets, mounted home or shell program enter this command.
    return ['/usr/bin/docker', 'exec', '--user', '10001:10001', '--workdir', '/opt/qa',
            'qa-worker', 'env', '-i', 'PATH=/usr/local/bin:/usr/bin:/bin', 'HOME=/tmp',
            'HTTP_PROXY=http://egress:8888', 'HTTPS_PROXY=http://egress:8888',
            'http_proxy=http://egress:8888', 'https_proxy=http://egress:8888',
            'NO_PROXY=backend,localhost,127.0.0.1', 'no_proxy=backend,localhost,127.0.0.1',
            'timeout', '--signal=TERM', '--kill-after=1s', '6s',
            'npm', '--silent', 'run', 'smoke']


def execute() -> tuple[int, bytes]:
    """Bound time and captured bytes; the container's independent timeout survives client loss."""
    process = subprocess.Popen(worker_command(), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,
                               env={'PATH': '/usr/bin:/bin', 'DOCKER_HOST': 'unix:///var/run/docker.sock',
                                    'DOCKER_CONFIG': '/etc/multica/qa/docker-client'},
                               start_new_session=True)
    selector = selectors.DefaultSelector()
    output = bytearray()
    total = 0
    deadline = time.monotonic() + 8
    try:
        for stream in (process.stdout, process.stderr):
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('job_timeout')
            for key, _ in selector.select(min(remaining, 0.2)):
                chunk = os.read(key.fileobj.fileno(), 8192)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > MAX_OUTPUT:
                    raise RuntimeError('job_output_limit')
                if key.fileobj is process.stdout:
                    output.extend(chunk)
        return process.wait(timeout=max(0.1, deadline - time.monotonic())), bytes(output)
    finally:
        selector.close()
        if process.poll() is None:
            process.kill()
        process.wait()
        for stream in (process.stdout, process.stderr):
            stream.close()


def public_report(data: bytes, exit_code: int) -> dict:
    """Only fixed labels, booleans and measured HTTP codes cross back to the model."""
    if len(data) > MAX_OUTPUT:
        raise ValueError('report_too_large')
    raw = json.loads(data)
    if not isinstance(raw, dict) or set(raw) != {'job', 'checks', 'passed'} or raw['job'] != JOB:
        raise ValueError('invalid_report')
    checks = raw['checks']
    if not isinstance(checks, list) or len(checks) != len(LABELS):
        raise ValueError('invalid_checks')
    safe = []
    for label, item in zip(LABELS, checks):
        if not isinstance(item, dict) or set(item) != {'name', 'pass', 'status'} or item['name'] != label:
            raise ValueError('invalid_check')
        if type(item['pass']) is not bool or type(item['status']) is not int or not 0 <= item['status'] <= 599:
            raise ValueError('invalid_check_value')
        # A failed HTTP check can never be promoted by a worker-supplied pass flag.
        passed = item['pass'] and 200 <= item['status'] < 300
        safe.append({'name': label, 'pass': passed, 'status': item['status']})
    passed = exit_code == 0 and all(check['pass'] for check in safe)
    if type(raw['passed']) is not bool or raw['passed'] != passed:
        raise ValueError('inconsistent_report')
    return {'job': JOB, 'checks': safe, 'passed': passed, 'exit_code': exit_code}


class Controller:
    def __init__(self, runner=execute, clock=time.monotonic, quota=None):
        self.runner, self.clock = runner, clock
        self.quota = quota
        self.lock = threading.Lock()
        self.started = deque()

    def run(self) -> tuple[int, dict]:
        if not self.lock.acquire(blocking=False):
            return 409, {'error': 'qa_busy'}
        try:
            now = self.clock()
            while self.started and now - self.started[0] >= 300:
                self.started.popleft()
            if len(self.started) >= 3:
                return 429, {'error': 'qa_rate_limited'}
            if self.quota is not None:
                try:
                    if not self.quota.reserve():
                        return 429, {'error': 'qa_budget_exhausted'}
                except Exception:
                    return 503, {'error': 'qa_budget_unavailable'}
            self.started.append(now)
            try:
                code, data = self.runner()
                return 200, public_report(data, code)
            except Exception:
                # Neither untrusted stdout/stderr nor exception text is logged or returned.
                return 502, {'error': 'qa_failed_or_invalid_report'}
        finally:
            self.lock.release()


def handler(controller: Controller, peers=frozenset({'10.250.0.4'})):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        allowed_peers = peers

        def log_message(self, *_):
            pass

        def setup(self):
            super().setup()
            self.connection.settimeout(5)

        def reply(self, status, body):
            payload = json.dumps(body, separators=(',', ':')).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(payload)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.wfile.write(payload)
            self.close_connection = True

        def do_POST(self):
            if self.client_address[0] not in peers:
                self.reply(403, {'error': 'peer_not_allowed'})
                return
            if self.path != '/run/platform-smoke':
                self.reply(404, {'error': 'unknown_fixed_job'})
                return
            if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Content-Length', []) not in ([], ['0']):
                self.reply(400, {'error': 'job_takes_no_payload'})
                return
            self.reply(*controller.run())

        def do_GET(self):
            self.reply(405, {'error': 'method_not_allowed'})

    return Handler


class Server(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def __init__(self, address, request_handler, *, tls_context=None, handshake_timeout=3):
        self.tls_context = tls_context
        self.handshake_timeout = handshake_timeout
        super().__init__(address, request_handler)

    def process_request_thread(self, request, client_address):
        if self.tls_context is None:
            return super().process_request_thread(request, client_address)
        # Do not perform TLS in accept(): one peer withholding ClientHello must not block every client.
        if client_address[0] not in self.RequestHandlerClass.allowed_peers:
            self.shutdown_request(request)
            return
        secured = None
        try:
            request.settimeout(self.handshake_timeout)
            secured = self.tls_context.wrap_socket(request, server_side=True, do_handshake_on_connect=False)
            secured.settimeout(self.handshake_timeout)
            secured.do_handshake()
        except OSError:
            self.shutdown_request(secured if secured is not None else request)
            return
        super().process_request_thread(secured, client_address)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cert', required=True, type=Path)
    parser.add_argument('--key', required=True, type=Path)
    parser.add_argument('--state-dir', type=Path, default=Path('/var/lib/multica-qa'))
    args = parser.parse_args()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.cert, args.key)
    server = Server(('10.250.0.1', 8443), handler(Controller(quota=Quota(args.state_dir))), tls_context=context)
    server.serve_forever(poll_interval=0.25)


if __name__ == '__main__':
    main()
