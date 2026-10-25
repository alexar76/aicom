#!/usr/bin/env python3
"""Linux-only, synthetic default-purchase experiment. Never invokes real paid services."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from billing_backend import start_backend

STUDY = Path('/study')
OUT = Path('/out')
FIXTURE = STUDY / 'fake-billing-server.mjs'
WARDEN = Path('/warden/package/dist/mcp-server.js')
spec = importlib.util.spec_from_file_location('histor_observer_under_test', STUDY / 'histor_observe.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
ObserverSession = observer.Session
NODE = shutil.which('node')


def save(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line] if path.exists() else []


class RecordingSession(ObserverSession):
    """Same newline protocol, additionally recording traffic and scripted consent controls."""
    def __init__(self, proc, deadline, transcript, answers=None):
        super().__init__(proc, deadline)
        self.transcript = transcript
        self.answers = iter(answers or [])
        self.prompts = []

    def note(self, direction, message):
        self.transcript.append({'sequence': len(self.transcript) + 1, 'monotonicNs': time.monotonic_ns(),
                                'direction': direction, 'message': message})

    def send(self, message):
        self.note('client_to_server', message)
        super().send(message)

    def _lines(self, until):
        for raw in super()._lines(until):
            try:
                self.note('server_to_client', json.loads(raw))
            except ValueError:
                self.note('server_to_client_noise', raw.decode(errors='replace'))
            yield raw

    def call(self, rid, method, params, wait_s):
        self.send({'jsonrpc': '2.0', 'id': rid, 'method': method, 'params': params})
        for raw in self._lines(time.monotonic() + wait_s):
            try:
                message = json.loads(raw)
            except ValueError:
                self.keep(raw)
                continue
            if not isinstance(message, dict):
                continue
            if message.get('id') == rid and ('result' in message or 'error' in message):
                return message
            if message.get('method') == 'elicitation/create' and 'id' in message:
                self.prompts.append(message)
                decision = next(self.answers, 'decline')
                content = {'run': True} if decision == 'accept' else {'run': False}
                result = {'action': 'accept' if decision in ('accept', 'unchecked') else 'decline', 'content': content}
                self.send({'jsonrpc': '2.0', 'id': message['id'], 'result': result})
            elif 'method' in message and 'id' in message:
                reply = {'roots': []} if message['method'] == 'roots/list' else None
                self.send({'jsonrpc': '2.0', 'id': message['id'], **({'result': reply} if reply is not None else
                          {'error': {'code': -32601, 'message': 'not supported by experiment client'}})})
        raise EOFError


def make_cases():
    # Each row receives its own server, backend, pin store and journals.
    return [
        dict(name='discovery-only', calls=[], charges=0),
        dict(name='histor-current-canary', observer=True, charges=0),
        dict(name='empty-default-purchase', calls=[{}], charges=1),
        dict(name='omitted-arguments', calls=[None], charges=1),
        dict(name='explicit-preview', calls=[{'mode': 'preview'}], charges=0),
        dict(name='explicit-purchase', calls=[{'mode': 'purchase'}], charges=1),
        dict(name='invalid-placeholder', calls=[{'mode': 'histor canary synthetic'}], charges=0, tool_error=True),
        dict(name='hidden-schema-default', config={'SCHEMA_DEFAULT': 'hidden'}, calls=[{}], charges=1),
        dict(name='required-mode-refuses-empty', config={'REQUIRE_MODE': 'true'}, calls=[{}], charges=0, tool_error=True),
        dict(name='charge-before-tool-error', config={'OUTCOME': 'error'}, calls=[{}], charges=1, tool_error=True),
        dict(name='charge-before-timeout', config={'OUTCOME': 'silent'}, calls=[{}], charges=1, timeout=True),
        dict(name='uncharged-matched-control', config={'CHARGE_ON': 'none'}, calls=[{}], charges=0),
        dict(name='readonly-hint-is-not-billing-proof', config={'READ_ONLY': 'true'}, calls=[{}], charges=1),
        dict(name='idempotent-purchase-retry', calls=[{'mode': 'purchase', 'idempotencyKey': 'same-operation'},
                                                   {'mode': 'purchase', 'idempotencyKey': 'same-operation'}], charges=1),
        dict(name='initialize-side-effect', config={'CHARGE_ON': 'initialize'}, calls=[], charges=1),
        dict(name='list-side-effect', config={'CHARGE_ON': 'tools/list'}, calls=[], charges=1),
        dict(name='warden-default-empty', wrap=True, calls=[{}], charges=1, prompts=0),
        dict(name='warden-sensitive-no-ui', wrap=True, sensitive=True, calls=[{}], charges=0, prompts=0, rpc_error=True),
        dict(name='warden-sensitive-decline', wrap=True, sensitive=True, ui=True, answers=['decline'], calls=[{}], charges=0, prompts=1, rpc_error=True),
        dict(name='warden-sensitive-unchecked', wrap=True, sensitive=True, ui=True, answers=['unchecked'], calls=[{}], charges=0, prompts=1, rpc_error=True),
        dict(name='warden-sensitive-accept', wrap=True, sensitive=True, ui=True, answers=['accept'], calls=[{}], charges=1, prompts=1),
        dict(name='warden-sensitive-one-approval', wrap=True, sensitive=True, ui=True, answers=['accept', 'decline'], calls=[{}, {}], charges=1, prompts=2, last_rpc_error=True),
        dict(name='warden-sensitive-refuse', wrap=True, sensitive=True, ui=True, refuse=True, calls=[{}], charges=0, prompts=0, rpc_error=True),
        dict(name='warden-sensitive-initialize-side-effect', wrap=True, sensitive=True, config={'CHARGE_ON': 'initialize'}, calls=[], charges=1, prompts=0),
        dict(name='warden-sensitive-list-side-effect', wrap=True, sensitive=True, config={'CHARGE_ON': 'tools/list'}, calls=[], charges=1, prompts=0),
        dict(name='explicit-price-description-default-wrap', wrap=True, config={'TOOL': 'purchase_report'}, calls=[{}], charges=1, prompts=0),
    ]


def run_case(case, repeat):
    name = case['name']
    run_id = f'{name}-{repeat}'
    directory = OUT / 'cases' / name / f'{repeat:02d}'
    directory.mkdir(parents=True, exist_ok=False)
    backend_dir = Path(tempfile.mkdtemp(prefix='kevin-bill-'))
    socket = backend_dir / 'b.sock'
    transcript, replies = [], []
    timed_out = False
    marks = {}
    result = {'case': name, 'repeat': repeat, 'runId': run_id, 'expectation': case}
    errors = []
    proc = None
    session = None
    env = dict(os.environ)
    for key in list(env):
        if key.startswith(('WARDEN_', 'HISTOR_')):
            del env[key]
    env.update({'WARDEN_FAKE_BILLING_LEDGER': str(directory / 'server-events.jsonl'),
                'WARDEN_FAKE_BILLING_SOCKET': str(socket), 'WARDEN_FAKE_BILLING_RUN_ID': run_id,
                **{'WARDEN_FAKE_BILLING_' + key: value for key, value in case.get('config', {}).items()}})
    command = [NODE, str(FIXTURE)]
    if case.get('wrap'):
        command = [NODE, str(WARDEN), 'wrap', '--id', 'fake-records', '--state-dir', str(directory / 'pins')]
        if case.get('sensitive'):
            policy = directory / 'policy.json'
            save(policy, {'sensitiveToolPatterns': ['lookup_record', 'purchase_report']})
            command += ['--policy', str(policy)]
        if case.get('refuse'):
            command += ['--ask', 'refuse']
        command += ['--', NODE, str(FIXTURE)]
    result['command'] = command
    try:
        with start_backend(socket, directory / 'billing.jsonl'):
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, start_new_session=True)
            if case.get('observer'):
                # The original talk and canary_args execute unchanged. Its `traced` parameter
                # enables calls; this run does not pretend to collect a gVisor syscall trace.
                observer.Session = lambda p, d: RecordingSession(p, d, transcript)
                try:
                    result['observerResult'] = observer.talk(proc, time.monotonic(), tag='kevin-fixed', traced=True, marks=marks)
                    result['observerMarks'] = marks
                finally:
                    observer.Session = ObserverSession
            else:
                session = RecordingSession(proc, time.monotonic() + 15, transcript, case.get('answers'))
                capabilities = {'elicitation': {}} if case.get('ui') else {}
                replies.append(session.call(1, 'initialize', {'protocolVersion': '2025-06-18', 'capabilities': capabilities,
                                       'clientInfo': {'name': 'synthetic-billing-check', 'version': '1'}}, 5))
                session.send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
                replies.append(session.call(2, 'tools/list', {}, 5))
                for index, args in enumerate(case.get('calls', [])):
                    params = {'name': case.get('config', {}).get('TOOL', 'lookup_record')}
                    if args is not None:
                        params['arguments'] = args
                    try:
                        replies.append(session.call(index + 3, 'tools/call', params, 0.7 if case.get('timeout') else 5))
                    except TimeoutError:
                        timed_out = True
                        break
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=2)
    except Exception as exc:
        errors.append(f'{type(exc).__name__}: {exc}')
    finally:
        if proc is not None and proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait(timeout=2)
        if proc is not None:
            (directory / 'stderr.txt').write_bytes(proc.stderr.read())
        if session is not None:
            session.sel.close()
        shutil.rmtree(backend_dir)
    billing = read_jsonl(directory / 'billing.jsonl')
    events = read_jsonl(directory / 'server-events.jsonl')
    prompts = [row for row in transcript if isinstance(row['message'], dict) and row['direction'] == 'server_to_client'
               and row['message'].get('method') == 'elicitation/create']
    result.update({'replies': replies, 'timedOut': timed_out, 'charges': len(billing),
                   'mockCredits': sum(row['credits'] for row in billing), 'prompts': len(prompts),
                   'toolHandlersStarted': sum(row['event'] == 'handler_start' and row.get('method') == 'tools/call' for row in events)})
    if len(billing) != case['charges']:
        errors.append(f'Expected {case["charges"]} charges, got {len(billing)}')
    if result['mockCredits'] != 7 * case['charges']:
        errors.append('Mock credit total disagrees with expected charged operations')
    if 'prompts' in case and len(prompts) != case['prompts']:
        errors.append('Unexpected number of approval prompts')
    if timed_out != case.get('timeout', False):
        errors.append('Unexpected timeout outcome')
    last_reply = replies[-1] if replies else {}
    if case.get('tool_error') and not last_reply.get('result', {}).get('isError'):
        errors.append('Expected tool isError after handler outcome')
    if (case.get('rpc_error') or case.get('last_rpc_error')) and 'error' not in last_reply:
        errors.append('Expected proxy refusal')
    if case.get('sensitive') and not case['charges'] and result['toolHandlersStarted']:
        errors.append('Refused tool invocation reached backend handler')
    if case.get('observer'):
        if result.get('observerResult', {}).get('status') != 'ok' or marks.get('coverage', {}).get('successful') != 1:
            errors.append('Original observer did not complete its canary call')
        resolved = [row for row in events if row['event'] == 'arguments_resolved']
        if len(resolved) != 1 or resolved[0]['mode'] != 'preview':
            errors.append('Original canary did not select preview as expected')
    for row in billing:
        if row.get('runId') != run_id:
            errors.append('Cross-run billing contamination')
    result['passed'] = not errors
    result['errors'] = errors
    save(directory / 'transcript.json', transcript)
    save(directory / 'result.json', result)
    return result


def main():
    assert sys.platform == 'linux', 'Synthetic runtime measurements run on Linux only'
    assert NODE and FIXTURE.is_file() and WARDEN.is_file()
    cases = make_cases()
    rows = []
    for repeat in range(1, 4):
        for case in cases:
            row = run_case(case, repeat)
            rows.append(row)
            print(f'{"PASS" if row["passed"] else "FAIL"} {row["case"]} repeat={repeat} charges={row["charges"]} prompts={row["prompts"]}', flush=True)
    pair_checks = []
    for repeat in range(1, 4):
        def wire(name):
            return [{key: row[key] for key in ('direction', 'message')} for row in
                    json.loads((OUT / 'cases' / name / f'{repeat:02d}' / 'transcript.json').read_text())]
        same = wire('empty-default-purchase') == wire('uncharged-matched-control')
        pair_checks.append({'name': 'Same complete MCP exchange, different billing ledger', 'repeat': repeat, 'passed': same})
    summary = {'type': 'kevin.synthetic-default-billing.v1', 'recordedAt': time.time(), 'platform': sys.platform,
               'node': subprocess.check_output([NODE, '--version'], text=True).strip(),
               'python': sys.version.split()[0], 'wardenVersion': json.loads(Path('/warden/package/package.json').read_text())['version'],
               'scenarios': len(cases), 'repeats': 3, 'runs': len(rows),
               'passedRuns': sum(row['passed'] for row in rows), 'failedRuns': sum(not row['passed'] for row in rows),
               'matchedTranscriptControls': pair_checks, 'realMoneyUsed': False, 'externalNetworkUsed': False,
               'observerTalkExecuted': True, 'gvisorTraceCollected': False,
               'limitations': ['Controlled synthetic fixtures do not estimate prevalence in the original census.',
                               'No real user awareness or real provider settlement was measured.',
                               'Approval answers are scripted protocol controls, not responses from human participants.',
                               'Ledger belongs to the separate mock billing process; provider-side charges cannot be inferred from MCP response alone.'],
               'results': [{key: row[key] for key in ('case', 'repeat', 'charges', 'mockCredits', 'prompts', 'timedOut', 'passed', 'errors')} for row in rows]}
    save(OUT / 'result.json', summary)
    assert not summary['failedRuns'] and all(check['passed'] for check in pair_checks), 'Preserve failed experiment evidence'
    print(json.dumps({key: summary[key] for key in ('scenarios', 'runs', 'passedRuns', 'failedRuns', 'matchedTranscriptControls')}, indent=2))


if __name__ == '__main__':
    main()
