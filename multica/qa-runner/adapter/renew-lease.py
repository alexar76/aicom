#!/usr/bin/env python3
"""Root infrastructure lease. Only a pinned fixed operation is renewed; flow/session state is never reset."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import time

URL = 'https://10.250.0.1:8443/run/platform-smoke'
WINDOW = 12 * 3600
MAX_USES = 10
DEFAULT_STATE = Path('/var/lib/docker/volumes/multica_daemon_home/_data/.local/state/warden')
DEFAULT_POLICY = Path('/opt/multica/opencode-guard/flow-policy.json')
DEFAULT_PRIVATE = Path('/opt/multica/opencode-guard/qa-adapter/private')

def encoded(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()

def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON key')
        value[key] = item
    return value

def document(path, owner_uid=0):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner_uid or info.st_mode & 0o022 or info.st_size > 262144:
            raise ValueError('unsafe protected configuration file')
        with os.fdopen(fd, 'r', closefd=False) as handle:
            value = json.load(handle, object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError('configuration must be an object')
        return value
    finally:
        os.close(fd)

def directory(path):
    """Walk by open directory descriptors: node-owned ancestors cannot redirect a privileged write via symlinks."""
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('absolute directory required')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            following = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = following
        return fd
    except BaseException:
        os.close(fd)
        raise

def atomic(path, data, mode):
    parent = directory(Path(path).parent)
    temporary = '.qa-lease-' + secrets.token_hex(12)
    fd = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
        with os.fdopen(fd, 'wb', closefd=False) as handle:
            handle.write(data); handle.flush()
        os.fchmod(fd, mode); os.fsync(fd); os.close(fd); fd = None
        os.replace(temporary, Path(path).name, src_dir_fd=parent, dst_dir_fd=parent)
        os.fsync(parent)
    finally:
        if fd is not None:
            os.close(fd)
        try:
            os.unlink(temporary, dir_fd=parent)
        except FileNotFoundError:
            pass
        os.close(parent)

def lease(now):
    epoch = int(now) // WINDOW
    start = epoch * WINDOW
    return {
        'version': 1,
        'taskId': 'qa_platform_smoke_' + datetime.fromtimestamp(start, timezone.utc).strftime('%Y%m%dT%H'),
        'expiresAt': datetime.fromtimestamp(start + 23 * 3600, timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z'),
        'transport': 'https', 'resources': [],
        'operations': [{'id': 'platform_smoke', 'title': 'Run the fixed secretless platform smoke check', 'maxUses': MAX_USES,
                        'request': {'method': 'POST', 'url': URL, 'headers': {'accept': 'application/json'}}}],
    }

def policy_for(existing, manifest):
    policy = dict(existing or {})
    if policy.get('mode', 'ask') != 'ask':
        raise ValueError('refusing to reset or weaken an existing non-ask policy')
    previous = policy.get('taskAdapter')
    if previous is not None and (not isinstance(previous, dict) or set(previous) != {'mode', 'server', 'manifestSha256'} or previous.get('server') != 'qa_runner' or previous.get('mode') != 'capabilities'):
        raise ValueError('an existing different/revoked task adapter needs operator review')
    policy.setdefault('mode', 'ask')
    policy['taskAdapter'] = {'mode': 'capabilities', 'server': 'qa_runner', 'manifestSha256': hashlib.sha256(manifest).hexdigest()}
    return policy

def renew(state_dir, policy_path, private_dir, now, apply=False, owner_uid=0):
    private = directory(private_dir)
    lock = None
    try:
        info = os.fstat(private)
        if info.st_uid != owner_uid or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError('lease metadata directory must be owner-only')
        if apply:
            lock = os.open('renew.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=private)
            if os.fstat(lock).st_uid != owner_uid:
                raise ValueError('unsafe renewal lock')
            fcntl.flock(lock, fcntl.LOCK_EX)
        epoch = int(now) // WINDOW
        previous = document(Path(private_dir) / 'lease-state.json', owner_uid)
        if previous is not None and (set(previous) != {'epoch', 'manifestSha256'} or not isinstance(previous['epoch'], int) or epoch < previous['epoch']):
            raise ValueError('lease clock/state check failed')
        manifest = encoded(lease(now))
        policy = policy_for(document(policy_path, owner_uid), manifest)
        pin = policy['taskAdapter']['manifestSha256']
        if previous and previous['epoch'] == epoch and previous['manifestSha256'] != pin:
            raise ValueError('same-window capability drift needs operator review')
        if apply:
            # A crash between these writes fails closed on a pin mismatch. No task usage, fingerprints or session file is opened for writing.
            atomic(Path(state_dir) / 'task-manifest.json', manifest, 0o444)
            atomic(policy_path, encoded(policy), 0o644)
            atomic(Path(private_dir) / 'lease-state.json', encoded({'epoch': epoch, 'manifestSha256': pin}), 0o600)
        return {'applied': apply, 'taskId': lease(now)['taskId'], 'expiresAt': lease(now)['expiresAt'],
                'maxUsesPer12h': MAX_USES, 'manifestSha256': pin, 'policyMode': policy['mode'],
                'sessionStateReset': False, 'usageBudgetResetWithinWindow': False}
    finally:
        if lock is not None:
            os.close(lock)
        os.close(private)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state-dir', type=Path, default=DEFAULT_STATE)
    parser.add_argument('--policy', type=Path, default=DEFAULT_POLICY)
    parser.add_argument('--private-dir', type=Path, default=DEFAULT_PRIVATE)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.apply and os.geteuid() != 0:
        parser.error('only root infrastructure may renew a live capability')
    print(json.dumps(renew(args.state_dir, args.policy, args.private_dir, time.time(), args.apply), indent=2))

if __name__ == '__main__':
    main()
