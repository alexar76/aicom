"""Verify the HISTOR fixture against mcp-rc-check. Use --feature to call surface lock --only."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

FIXTURE = Path(__file__).with_name('histor-review-one.json')
RULE = 'tool-description-changed'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('cli', type=Path, help='Path to the built mcp-rc-check dist/cli.js')
    parser.add_argument('--feature', action='store_true', help='Exercise a build that implements --only')
    args = parser.parse_args()
    cli = args.cli.resolve(strict=True)
    case = json.loads(FIXTURE.read_text())
    reviewed = case['accept_only']
    current = {t['name']: t for t in case['current']}

    with tempfile.TemporaryDirectory(prefix='histor-partial-review-') as tmp:
        root = Path(tmp)
        before_dump, current_dump, projected_dump = (root / f'{name}.json' for name in
                                                       ('before', 'current', 'projected'))
        pin = root / 'mcp-surface.lock.json'
        projected = [current[reviewed] if t['name'] == reviewed else t for t in case['before']]
        for dump, tools in ((before_dump, case['before']), (current_dump, case['current']),
                            (projected_dump, projected)):
            dump.write_text(json.dumps({'tools': tools}))

        def run(*flags, expected=0):
            p = subprocess.run(['node', str(cli), 'surface', *flags], text=True,
                               capture_output=True, timeout=15)
            if p.returncode != expected:
                raise RuntimeError(f'{p.returncode} for {flags}: {p.stderr}\n{p.stdout}')
            return p.stdout

        def verify(expected_tools):
            raw = run('verify', '--dump', str(current_dump), '--lock', str(pin), '--format', 'json',
                      expected=1 if expected_tools else 0)
            result = json.loads(raw)
            assert result['errors'] == [], result
            actual = sorted((entry['ruleId'], entry['tool']) for entry in result['changes'])
            assert actual == sorted((RULE, tool) for tool in expected_tools), actual
            return [tool for _, tool in actual]

        run('lock', '--dump', str(before_dump), '--out', str(pin), '--require', 'list_zones')
        baseline = json.loads(pin.read_text())
        before = verify(case['changed'])
        if args.feature:
            run('lock', '--dump', str(current_dump), '--out', str(pin), '--only', reviewed)
        else:
            run('lock', '--dump', str(projected_dump), '--out', str(pin), '--require', 'list_zones')
        after = verify(set(case['changed']) - {reviewed})
        updated = json.loads(pin.read_text())
        assert baseline['toolOrder'] == updated['toolOrder']
        assert baseline['tools'].keys() == updated['tools'].keys()
        changed_pins = sorted(n for n in updated['tools'] if baseline['tools'][n] != updated['tools'][n])
        assert changed_pins == [reviewed], changed_pins
        control = updated['tools'][case['unchanged_control']]
        assert control['definition'] == current[case['unchanged_control']] and control['required']
        print(json.dumps({'event_id': case['event_id'], 'cli_version': updated['generatorVersion'],
                          'mode': 'native --only' if args.feature else 'expected partial pin',
                          'changes_before': before, 'changes_after': after,
                          'updated_pin': reviewed, 'unchanged_control': case['unchanged_control']}, indent=2))


if __name__ == '__main__':
    main()
