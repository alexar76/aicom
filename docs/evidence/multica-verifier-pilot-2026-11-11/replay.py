#!/usr/bin/env python3
"""Replay the checked-out Multica platform_smoke job against offline inputs."""

from hashlib import sha256
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from unittest.mock import patch
from uuid import UUID


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
WORKER = ROOT / 'multica/qa-runner/worker/smoke.mjs'
BROKER = ROOT / 'multica/qa-runner/broker/broker.py'
ACCEPTANCE = ROOT / 'artifacts/multica-qa-runner-2026-11-10/create-profile.py'
PROBE = HERE / 'probe.mjs'
EXECUTE_TOOL = 'qa_runner_task_execute'


def load_source(path):
    spec = spec_from_file_location(path.stem, path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def replay_case(broker, helper, node, name, task_number, fixture_status, withhold_report):
    command = [node, '--import', f'{PROBE.as_uri()}?modelmarket={fixture_status}', str(WORKER)]
    # The production broker still starts and bounds the subprocess and validates
    # its exit and report. The local command is fixed by this script, not input.
    with patch.object(broker, 'worker_command', return_value=command):
        controller_status, report = broker.Controller().run()
    if controller_status != 200:
        raise RuntimeError(f'{name}: controller rejected the fixture ({controller_status})')

    task_id = str(UUID(int=task_number))
    tool_result_id = str(UUID(int=99)) if withhold_report else task_id
    tool_output = json.dumps({'status': controller_status, 'untrusted': True, 'text': json.dumps(report)})
    events = [
        {'task_id': task_id, 'type': 'tool_use', 'tool': EXECUTE_TOOL, 'output': ''},
        {'task_id': tool_result_id, 'type': 'tool_result', 'tool': EXECUTE_TOOL, 'output': tool_output},
    ]
    # Emulate snapshot()'s task_id filter before using the existing summarizer.
    # In the last case the passing tool report belongs to a different task.
    messages = [event for event in events if event['task_id'] == task_id]
    same_task_reports = [json.loads(json.loads(event['output'])['text']) for event in messages
                         if event['type'] == 'tool_result' and event['tool'] == EXECUTE_TOOL]
    if same_task_reports and same_task_reports != [report]:
        raise RuntimeError(f'{name}: stored report does not match the worker output')

    # All three rows have a completed task, a tool invocation and a final result
    # that claims success. The required evidence is the actual tool result.
    claimed_result = ' '.join([helper.MARKER, *helper.LABELS, 'passed'])
    summary = helper.summarize({
        'issue_owned': True,
        'tasks': [{'id': task_id, 'status': 'completed', 'result': claimed_result}],
        'message_count': len(messages),
        'messages': messages,
        'comments': [claimed_result],
    })
    if not same_task_reports:
        verdict = 'unverifiable'
    elif report['passed'] is False:
        verdict = 'fail'
    elif summary['passed'] is True:
        verdict = 'pass'
    else:
        verdict = 'unverifiable'

    return {
        'case': name,
        'verdict': verdict,
        'completed': summary['completed'],
        'qa_execute_calls': summary['qa_execute_calls'],
        'controller_status': controller_status,
        'local_worker_exit_code': report['exit_code'],
        'local_worker_http_statuses': {check['name']: check['status'] for check in report['checks']},
        'same_task_tool_report': bool(same_task_reports),
        'foreign_tool_reports_excluded': len(events) - len(messages),
        'multica_acceptance_passed': summary['passed'],
    }


def main():
    if len(sys.argv) != 1:
        print('The offline replay takes no arguments.', file=sys.stderr)
        return 2
    node = shutil.which('node')
    if node is None:
        print('The replay needs Node 22.15+ on PATH.', file=sys.stderr)
        return 2
    node = str(Path(node).resolve())
    version_check = subprocess.run(
        [node, '-e', 'if (!require("node:module").registerHooks) process.exit(1); console.log(process.version)'],
        env={}, capture_output=True, text=True, timeout=5,
    )
    if version_check.returncode != 0:
        print('The replay needs Node 22.15+ for module hooks.', file=sys.stderr)
        return 2
    version = version_check.stdout.strip()

    broker = load_source(BROKER)
    helper = load_source(ACCEPTANCE)
    cases = [
        replay_case(broker, helper, node, 'healthy', 1, 200, withhold_report=False),
        replay_case(broker, helper, node, 'required_check_failed', 2, 503, withhold_report=False),
        replay_case(broker, helper, node, 'missing_same_task_report', 3, 200, withhold_report=True),
    ]
    observed = [(case['verdict'], case['local_worker_exit_code'], tuple(case['local_worker_http_statuses'].values()),
                 case['same_task_tool_report'],
                 case['foreign_tool_reports_excluded'], case['multica_acceptance_passed']) for case in cases]
    matched = observed == [
        ('pass', 0, (200, 200, 200), True, 0, True),
        ('fail', 1, (200, 503, 200), True, 0, False),
        ('unverifiable', 0, (200, 200, 200), False, 1, False),
    ] and all(case['completed'] and case['qa_execute_calls'] == 1 and case['controller_status'] == 200
              for case in cases)
    result = {
        'schema': 'multica-verifier-pilot/v1',
        'environment': {'python': platform.python_version(), 'node': version,
                        'system': platform.system(), 'architecture': platform.machine()},
        'source_sha256': {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest()
                          for path in (WORKER, BROKER, ACCEPTANCE, PROBE, HERE / 'replay.py')},
        'cases': cases,
        'matched_expected': matched,
    }
    print(json.dumps(result, indent=2))
    return 0 if matched else 1


if __name__ == '__main__':
    sys.exit(main())
