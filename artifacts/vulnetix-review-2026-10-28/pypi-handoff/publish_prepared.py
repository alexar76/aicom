#!/usr/bin/env python3
"""Publisher entry point. Default: local checks only; upload requires --upload-to-pypi."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import verify_release

HERE = Path(__file__).resolve().parent


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--upload-to-pypi', action='store_true', help='operator-only: publish the exact prepared wheels')
    args = parser.parse_args(argv)
    if verify_release.main(['--local-only']):
        return 1
    if not args.upload_to_pypi:
        print('Prepared only. No network, credential reads or uploads. The designated publisher runs --upload-to-pypi.')
        return 0
    # This branch is for the designated publisher, who supplies their own credential.
    token = os.environ.get('UV_PUBLISH_TOKEN')
    if not token:
        print('Publisher must provide UV_PUBLISH_TOKEN through their own credential setup.', file=sys.stderr)
        return 2
    uv = shutil.which('uv')
    if not uv:
        print('Publisher needs the uv command.', file=sys.stderr)
        return 2
    if verify_release.main(['--availability', '--report', str(HERE/'pre-upload-availability.json')]):
        return 1
    env = {key: value for key, value in os.environ.items() if not key.startswith(('UV_', 'TWINE_', 'PYPI_'))}
    env['UV_PUBLISH_TOKEN'] = token
    plan = json.loads((HERE/'publication-plan.json').read_text())
    for entry in plan['packages']:
        command = [uv, 'publish', '--no-config', '--trusted-publishing', 'never',
                   '--publish-url', 'https://upload.pypi.org/legacy/',
                   '--check-url', 'https://pypi.org/simple/', str(HERE/'wheels'/entry['wheel'])]
        completed = subprocess.run(command, cwd=HERE, env=env)
        if completed.returncode:
            print('Publication stopped at '+entry['package']+'; inspect PyPI before retrying.', file=sys.stderr)
            return completed.returncode
    return verify_release.main(['--published', '--report', str(HERE/'published-verification.json')])


if __name__ == '__main__':
    raise SystemExit(main())
