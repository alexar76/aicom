#!/usr/bin/env python3
"""Run only these research scripts against the existing public dataset on admin-vps."""
import hashlib
import argparse
import json
from pathlib import Path
import shlex
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
IMAGE = 'sha256:79bc0c21f402e16b32ce00a2ac73782b9985ef9a8595adb936080db2c7b0cc13'
SSH = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=15', 'admin-vps']


def remote(args):
    return subprocess.check_output(SSH + [shlex.join(args)], text=True)


def stream(args, log):
    with (HERE / log).open('w') as handle:
        process = subprocess.Popen(SSH + [shlex.join(args)], stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            handle.write(line)
            handle.flush()
            # Keep the complete terminal log without flooding the conversation.
            print(line[:2000].rstrip(), flush=True)
        code = process.wait()
    if code:
        raise RuntimeError(f'{log}: exit {code}')


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--resume-runtime-failure', action='store_true')
    args = parser.parse_args()
    if args.resume_runtime_failure:
        metadata = json.loads((HERE / 'execution.json').read_text())
        assert metadata['state'] == 'prepared'
        root = metadata['remoteTemp']
        metadata['initialAttempt'] = {'runtime': 'runsc', 'exitCode': 125,
                                      'reason': 'Runtime not registered; no research code executed'}
        (HERE / 'tests.log').rename(HERE / 'runtime-unavailable.log')
    else:
        assert not (HERE / 'execution.json').exists(), 'Do not accidentally overwrite a prior run'
        root = remote(['mktemp', '-d', '/tmp/arhan-change-kinds-20261025.XXXXXX']).strip()
        metadata = {'startedAt': datetime.now(timezone.utc).isoformat(), 'host': 'admin-vps',
                    'remoteTemp': root, 'image': IMAGE, 'sources': {}, 'state': 'prepared'}
    assert root.startswith('/tmp/arhan-change-kinds-20261025.') and '/' not in root[5:]

    def save():
        (HERE / 'execution.json').write_text(json.dumps(metadata, indent=2) + '\n')

    save()
    remote(['mkdir', '-p', root + '/source', root + '/out'])
    remote(['chmod', '755', root, root + '/source'])
    remote(['chown', '65532:65532', root + '/out'])
    files = ['analyze.py', 'test_analyze.py', 'cohort_readonly.py', 'protocol.md']
    for name in files:
        metadata['sources'][name] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', *[str(HERE / f) for f in files],
                    'admin-vps:' + root + '/source/'], check=True)
    image_info = remote(['docker', 'image', 'inspect', '--format',
                         '{{json .Id}}|{{json .Os}}|{{json .Architecture}}', IMAGE]).strip()
    metadata['imageMetadata'] = json.loads('[' + image_info.replace('|', ',') + ']')
    container = ['docker', 'run', '--rm', '--runtime', 'runc', '--network', 'none', '--read-only',
                 '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges', '--memory', '1536m',
                 '--cpus', '1', '--pids-limit', '64', '--tmpfs', '/tmp:rw,nosuid,noexec,size=64m',
                 '--user', '65532:65532', '-v', root + '/source:/work:ro',
                 '-v', '/var/lib/histor-datasets/2026-10-20:/data:ro', '-v', root + '/out:/out:rw',
                 '--workdir', '/work', '--entrypoint', 'python', IMAGE, '-B', '-u']
    metadata['containerArguments'] = container
    save()
    stream(container + ['-m', 'unittest', 'discover', '-s', '/work', '-p', 'test_analyze.py', '-v'], 'tests.log')
    metadata['state'] = 'tests_passed'
    save()
    stream(container + ['/work/cohort_readonly.py', '/data'], 'cohort.log')
    stream(container + ['/work/analyze.py', '--data', '/data', '--out', '/out'], 'analysis.log')
    metadata['state'] = 'analysis_completed'
    save()
    for name in ['summary.json', 'transitions.jsonl', 'servers.jsonl', 'manifest.json']:
        subprocess.run(['scp', '-q', '-o', 'BatchMode=yes', 'admin-vps:' + root + '/out/' + name,
                        str(HERE / name)], check=True)
    metadata['finishedAt'] = datetime.now(timezone.utc).isoformat()
    metadata['state'] = 'downloaded_not_cleaned'
    save()
    print('Completed; evidence downloaded. Verify before removing remote temporary directory.', flush=True)


if __name__ == '__main__':
    main()
