"""Run the actual CLI against public textokit snapshots; data only, no MCP server execution."""
import contextlib
import datetime
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path

import histor
from histor import toolcost, toolcost_cli

P = Path('/example')
os.environ.pop('GITHUB_STEP_SUMMARY', None)


def cli(args):
    output, errors = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
        code = toolcost_cli.main(args)
    return {'args': args, 'exit_code': code, 'stdout': output.getvalue(), 'stderr': errors.getvalue()}


before, after = P / 'before-tools.json', P / 'after-tools.json'
baseline, reduced = P / 'baseline.json', P / 'reduced-baseline.json'
calls = [cli(['snapshot', '--tools', str(before), '-o', str(baseline)]),
         cli(['snapshot', '--tools', str(after), '-o', str(reduced)])]
assert all(c['exit_code'] == 0 for c in calls), calls
normal = cli(['check', '--baseline', str(baseline), '--tools', str(after), '--max-increase', '10%', '--json'])
reverse = cli(['check', '--baseline', str(reduced), '--tools', str(before), '--max-increase', '10%', '--json'])
assert normal['exit_code'] == 0, normal
assert reverse['exit_code'] == 1, reverse
n, r = json.loads(normal['stdout']), json.loads(reverse['stdout'])
expected = json.loads((P / 'cost.json').read_text())
assert n['diff']['totals'] == expected['totals']
assert n['diff']['toolCount'] == {'before': 20, 'after': 20, 'delta': 0}
assert n['diff']['totals']['sent'] == {'before': 5565, 'after': 3776, 'delta': -1789}
assert n['ok'] and not r['ok'] and len(r['problems']) == 3
(P / 'normal-check.json').write_text(json.dumps(n, indent=2) + '\n')
(P / 'reverse-check.json').write_text(json.dumps(r, indent=2) + '\n')
verification = {
    'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'histor_image_version': histor.__version__,
    'tiktoken_version': importlib.metadata.version('tiktoken'),
    'network_during_validation': 'none',
    'normal_exit_code': normal['exit_code'], 'reverse_exit_code': reverse['exit_code'],
    'all_totals_match_public_api': True,
    'module_sha256': {m.__name__: hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (toolcost, toolcost_cli)},
    'calls': calls + [normal, reverse],
}
(P / 'validation.json').write_text(json.dumps(verification, indent=2) + '\n')
print(json.dumps({k: v for k, v in verification.items() if k != 'calls'}))
