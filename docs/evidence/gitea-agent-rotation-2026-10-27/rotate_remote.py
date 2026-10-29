"""Authorized, root-only Gitea/agent rotation; secrets never enter stdout or argv.

Run with Python -I on admin-vps. Private handoff/state are under /run, never in
this repository. Only explicit non-secret projections are written as evidence.
"""

import base64
import contextlib
import fcntl
import http.cookiejar
import json
import os
import re
import secrets
import stat
import subprocess
import sys
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, ProxyHandler, Request, build_opener

ROOT = Path('/run/skopos-gitea-rotation-20261027')
ENV = Path('/etc/skopos-deploy-hand/env')
STORE = Path('/etc/skopos-deploy-hand/gitea-source.credentials')
UNIT = 'skopos-deploy-hand.service'
CONTAINER = 'gitea-gitea-1'
BASE = 'http://localhost:3000'
STEP = 'initialization'
MAX_BYTES = 2 * 1024 * 1024
GIT_SETTINGS = {
    'GIT_CONFIG_COUNT': '3',
    'GIT_CONFIG_KEY_0': 'credential.helper', 'GIT_CONFIG_VALUE_0': '',
    'GIT_CONFIG_KEY_1': 'credential.helper',
    'GIT_CONFIG_VALUE_1': f'store --file={STORE}',
    'GIT_CONFIG_KEY_2': 'credential.useHttpPath', 'GIT_CONFIG_VALUE_2': 'true',
    'GIT_TERMINAL_PROMPT': '0',
}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Forms(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tokens = set()
        self.fields = set()

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == 'input':
            self.fields.add(values.get('name'))
            if values.get('name') == '_csrf' and values.get('value'):
                self.tokens.add(values['value'])


def phase(name):
    global STEP
    STEP = name
    print(json.dumps({'at': datetime.now(UTC).isoformat(), 'phase': name}), flush=True)


def command(args, *, input_text=None, env=None, timeout=45):
    result = subprocess.run(args, input=input_text, env=env, capture_output=True,
                            text=True, timeout=timeout)
    if result.returncode or len(result.stdout.encode()) > MAX_BYTES:
        raise RuntimeError('Command failed; output withheld')
    return result.stdout


def atomic(path, data, mode=0o600):
    assert not path.is_symlink()
    temp = path.with_name('.' + path.name + '.' + secrets.token_hex(6))
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, mode)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def record(name, data):
    atomic(ROOT / name, (json.dumps(data, indent=2) + '\n').encode())


def request(opener, path, *, headers=None, form=None):
    assert path.startswith('/') and not path.startswith('//')
    data = urlencode(form).encode() if form is not None else None
    req = Request(BASE + path, data=data, headers=headers or {})
    try:
        with opener.open(req, timeout=25) as response:
            body = response.read(MAX_BYTES + 1)
            status, location = response.status, response.headers.get('Location')
    except HTTPError as error:
        body = error.read(MAX_BYTES + 1)
        status, location = error.code, error.headers.get('Location')
    assert len(body) <= MAX_BYTES
    if location:
        target = urlsplit(location)
        assert not target.netloc or (target.scheme, target.netloc) == ('http', 'localhost:3000')
    return status, body, location


def basic(username, password):
    return {'Authorization': 'Basic ' + base64.b64encode((username + ':' + password).encode()).decode()}


def api(username, password, path):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    status, body, _ = request(opener, '/api/v1' + path, headers=basic(username, password))
    return status, json.loads(body) if status == 200 else None


def settings():
    return dict(line.split('=', 1) for line in ENV.read_text().splitlines()
                if line and not line.startswith('#') and '=' in line)


def unit_state():
    text = command(['systemctl', 'show', UNIT,
                    '--property=ActiveState,SubState,MainPID,NRestarts,User'])
    return dict(line.split('=', 1) for line in text.splitlines() if '=' in line)


def loaded_git_settings(pid, clean):
    # Type=simple can report active before execve installs EnvironmentFile.
    expected = {key.encode(): value.encode() for key, value in GIT_SETTINGS.items()}
    expected[b'SKOPOS_AGENT_REPO_URL'] = clean.encode()
    for _ in range(50):
        state = unit_state()
        assert state['ActiveState'] == 'active' and state['MainPID'] == pid
        loaded = dict(item.split(b'=', 1) for item in Path('/proc/' + pid + '/environ').read_bytes().split(b'\0') if b'=' in item)
        if all(loaded.get(key) == value for key, value in expected.items()):
            return
        time.sleep(0.1)
    raise RuntimeError('Agent environment readiness timed out; values withheld')


def git_env(config):
    result = {key: value for key, value in os.environ.items()
              if not key.startswith('GIT_TRACE') and key not in ('GIT_CURL_VERBOSE', 'GIT_ASKPASS', 'SSH_ASKPASS')}
    result.update(config)
    return result


def git_checks(config, mirror, clean, username, token):
    env = git_env(config)
    context = 'protocol=http\nhost=localhost:3000\npath=alexar76/aicom.git\n\n'
    filled = command(['git', 'credential', 'fill'], input_text=context, env=env)
    values = dict(line.split('=', 1) for line in filled.splitlines() if '=' in line)
    assert secrets.compare_digest(values.get('password', ''), token) and values.get('username') == username
    negative = subprocess.run(['git', 'credential', 'fill'],
                             input=context.replace('alexar76/aicom.git', 'alexar76/unrelated.git'),
                             env=env, capture_output=True, text=True, timeout=15)
    assert token not in negative.stdout
    direct = command(['git', 'ls-remote', clean, 'refs/heads/main'], env=env)
    cached = command(['git', '--git-dir', str(mirror), 'ls-remote', 'origin', 'refs/heads/main'], env=env)
    assert re.fullmatch(r'[0-9a-f]{40}\s+refs/heads/main\s*', direct)
    assert direct.strip() == cached.strip()
    command(['git', '--git-dir', str(mirror), 'fetch', '--dry-run', '--no-tags', 'origin',
             'refs/heads/momus/fix-warden-0.22.2-metadata-4afe02438'], env=env)
    return {'helperMatchesNewCredential': True, 'otherPathDoesNotReceiveCredential': True,
            'directTransportPassed': True, 'cachedOriginTransportPassed': True,
            'allowedBranchFetchDryRunPassed': True, 'mainRevision': direct.split()[0]}


def web_session(username, password):
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(http.cookiejar.CookieJar()))
    phase('web-login-form')
    status, body, _ = request(opener, '/user/login?redirect_to=/user/settings/account')
    assert status == 200
    form = Forms()
    form.feed(body.decode())
    assert len(form.tokens) == 1
    phase('web-login-authentication')
    status, _, location = request(opener, '/user/login', form={
        '_csrf': next(iter(form.tokens)), 'user_name': username, 'password': password,
        'redirect_to': '/user/settings/account',
    })
    assert status in (302, 303) and location
    assert not any(part in location for part in ('two_factor', 'webauthn', 'captcha', '/user/login'))
    phase('web-password-form')
    status, body, _ = request(opener, '/user/settings/account')
    assert status == 200
    form = Forms()
    form.feed(body.decode())
    assert len(form.tokens) == 1 and {'old_password', 'password', 'retype'} <= form.fields
    return opener


def main(*, resume=False):
    assert os.geteuid() == 0
    os.umask(0o077)
    if not resume:
        ROOT.mkdir(mode=0o700, exist_ok=False)
    assert ROOT.stat().st_uid == 0 and stat.S_IMODE(ROOT.stat().st_mode) == 0o700
    with contextlib.ExitStack() as locks:
        for filename in ('/run/lock/skopos-gitea-rotation.lock', '/run/lock/histor-warden-operator.lock'):
            handle = locks.enter_context(open(filename, 'a'))
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        phase('preflight')
        original_env_bytes = ENV.read_bytes()
        original = settings()
        assert not any(key.startswith('GIT_CONFIG_') for key in original)
        u = urlsplit(original['SKOPOS_AGENT_REPO_URL'])
        username, old = unquote(u.username or ''), unquote(u.password or '')
        assert (u.scheme, u.hostname, u.port, u.path, username) == ('http', 'localhost', 3000, '/alexar76/aicom.git', 'alexar76')
        assert old
        if resume:
            assert (ROOT / 'token-created.json').is_file() and STORE.is_file()
            assert not any((ROOT / name).exists() for name in ('agent-switched.json', 'password-rotated.json', 'verified.json'))
            assert json.loads((ROOT / 'old-private.json').read_text())['url'] == original['SKOPOS_AGENT_REPO_URL']
            private = json.loads((ROOT / 'new-credentials.json').read_text())
            assert private['username'] == username and private['gitea'] == BASE
            assert api(username, private['password'], '/user')[0] == 401
        else:
            assert not STORE.exists()
        clean = urlunsplit((u.scheme, 'localhost:3000', u.path, '', ''))
        mirror = Path(original['SKOPOS_AGENT_STATE_DIR']) / 'repo.git'
        mirror_config = mirror / 'config'
        original_mirror_bytes = mirror_config.read_bytes()
        original_env_mode = stat.S_IMODE(ENV.stat().st_mode)
        original_mirror_mode = stat.S_IMODE(mirror_config.stat().st_mode)
        assert ENV.stat().st_uid == 0 and mirror_config.stat().st_uid == 0
        origin = command(['git', '--git-dir', str(mirror), 'config', '--get', 'remote.origin.url']).strip()
        assert origin == original['SKOPOS_AGENT_REPO_URL']
        status, user = api(username, old, '/user')
        assert status == 200 and user['login'] == username and user['id'] == 1 and user['is_admin'] and user['source_id'] == 0
        identity = {key: user[key] for key in ('id', 'login', 'is_admin', 'source_id', 'login_name')}
        before = unit_state()
        assert before['User'] == 'root' and before['ActiveState'] == 'active'
        pid = int(before['MainPID'])
        assert not Path(f'/proc/{pid}/task/{pid}/children').read_text().strip()
        web = web_session(username, old)
        record('resume-preflight.json' if resume else 'preflight.json', {'at': datetime.now(UTC).isoformat(), 'identity': identity,
                                 'agent': before, 'credentialKind': 'local-account-password',
                                 'targetUnchanged': True, 'webPasswordFormReady': True})
        atomic(ROOT / 'old-private.json', json.dumps({'url': origin}).encode())

        phase('create-agent-token')
        if resume:
            name = json.loads((ROOT / 'token-intent.json').read_text())['tokenName']
            token, password = private['deployAgentToken'], private['password']
        else:
            name = 'skopos-agent-repo-' + datetime.now(UTC).strftime('%Y%m%dT%H%M%S')
            record('token-intent.json', {'tokenName': name, 'scopes': ['read:repository']})
            raw = command(['docker', 'exec', '--user', 'git', '-e', 'GITEA_WORK_DIR=/var/lib/gitea', CONTAINER,
                       'gitea', '--work-path', '/var/lib/gitea', '--config', '/etc/gitea/app.ini',
                       'admin', 'user', 'generate-access-token', '--username', username,
                       '--token-name', name, '--scopes', 'read:repository', '--raw'])
            matches = [line.strip() for line in raw.splitlines() if re.fullmatch(r'[a-fA-F0-9]{40}', line.strip())]
            assert len(matches) == 1
            token = matches[0]
            password = secrets.token_urlsafe(36) + 'aA7!'
            # Capture the one-time token before any further validation can fail.
            atomic(ROOT / 'new-credentials.json', json.dumps({'gitea': BASE, 'username': username,
                                                       'password': password, 'deployAgentToken': token}).encode())
        status, tokens = api(username, old, '/users/' + username + '/tokens')
        matching = [row for row in tokens if row['name'] == name] if status == 200 else []
        assert len(matching) == 1 and matching[0]['scopes'] == ['read:repository']
        token_id = matching[0]['id']
        status, repo = api(username, token, '/repos/alexar76/aicom')
        assert status == 200 and repo['private'] and repo['owner']['login'] == username
        denied, _, _ = request(build_opener(ProxyHandler({}), NoRedirect()),
                               '/alexar76/aicom.git/info/refs?service=git-receive-pack',
                               headers=basic(username, token))
        assert denied == 403, 'Normal Basic Git write discovery was not denied'
        credential_url = urlunsplit(('http', quote(username, safe='') + ':' + quote(token, safe='') + '@localhost:3000', u.path, '', ''))
        atomic(STORE, (credential_url + '\n').encode())
        record('token-created.json', {'tokenId': token_id, 'tokenName': name, 'scopes': matching[0]['scopes'],
                                      'privateRepositoryReadPassed': True,
                                      'basicWriteDiscoveryStatus': denied,
                                      'noGitPushCommandUsed': True,
                                      'scopeIsUserWideRepositoryCategory': True})

        phase('switch-agent-to-protected-token')
        # All unrelated EnvironmentFile values are retained byte for byte.
        lines = ENV.read_text().splitlines()
        lines = [('SKOPOS_AGENT_REPO_URL=' + clean) if line.startswith('SKOPOS_AGENT_REPO_URL=') else line for line in lines]
        lines += [key + '=' + value for key, value in GIT_SETTINGS.items()]
        updated = '\n'.join(lines) + '\n'
        new_config = {**original, 'SKOPOS_AGENT_REPO_URL': clean, **GIT_SETTINGS}
        # Prove the new transport before stopping the agent; cached origin changes below.
        env = git_env(new_config)
        assert re.fullmatch(r'[0-9a-f]{40}\s+refs/heads/main\s*', command(['git', 'ls-remote', clean, 'refs/heads/main'], env=env))
        fresh = unit_state()
        assert fresh['MainPID'] == before['MainPID'] and fresh['ActiveState'] == 'active'
        assert not Path(f'/proc/{pid}/task/{pid}/children').read_text().strip()
        command(['systemctl', 'stop', UNIT])
        try:
            atomic(ENV, updated.encode(), stat.S_IMODE(ENV.stat().st_mode))
            command(['git', '--git-dir', str(mirror), 'config', 'remote.origin.url', clean])
            command(['systemctl', 'start', UNIT])
            after = unit_state()
            assert after['ActiveState'] == 'active' and int(after['MainPID']) != pid
            loaded_git_settings(after['MainPID'], clean)
            assert {k: v for k, v in settings().items() if k not in GIT_SETTINGS and k != 'SKOPOS_AGENT_REPO_URL'} == {k: v for k, v in original.items() if k not in GIT_SETTINGS and k != 'SKOPOS_AGENT_REPO_URL'}
            transport = git_checks(new_config, mirror, clean, username, token)
        except Exception:
            # Account password is still valid at this stage; restore the prior
            # configuration in memory, never a secret-bearing command argument.
            atomic(ENV, original_env_bytes, original_env_mode)
            atomic(mirror_config, original_mirror_bytes, original_mirror_mode)
            command(['systemctl', 'restart', UNIT])
            raise
        record('agent-switched.json', {'beforePid': pid, 'after': after, 'urlHasNoCredential': True,
                                      'originHasNoCredential': True, 'otherSettingsUnchanged': True,
                                      'credentialFileMode': oct(stat.S_IMODE(STORE.stat().st_mode)), **transport})

        phase('rotate-account-password')
        status, body, _ = request(web, '/user/settings/account')
        assert status == 200
        form = Forms()
        form.feed(body.decode())
        assert len(form.tokens) == 1
        status, _, location = request(web, '/user/settings/account', form={
            '_csrf': next(iter(form.tokens)), 'old_password': old,
            'password': password, 'retype': password,
        })
        assert status in (302, 303) and location
        old_status, _ = api(username, old, '/user')
        new_status, new_user = api(username, password, '/user')
        assert old_status == 401 and new_status == 200
        assert {key: new_user[key] for key in identity} == identity
        assert git_checks(new_config, mirror, clean, username, token)['cachedOriginTransportPassed']
        record('password-rotated.json', {'oldBasicStatus': old_status, 'newBasicStatus': new_status,
                                        'sameIdentityAndAuthSource': True, 'agentTokenStillWorks': True})
        (ROOT / 'old-private.json').unlink()

        phase('final-agent-verification')
        checkpoint = int(time.time())
        time.sleep(35)
        stable = unit_state()
        assert stable['ActiveState'] == 'active' and stable['MainPID'] == after['MainPID'] and stable['NRestarts'] == after['NRestarts']
        journal = command(['journalctl', '-u', UNIT, '_PID=' + after['MainPID'],
                           '--since', '@' + str(checkpoint), '-o', 'cat', '--no-pager'])
        polls = len(re.findall(r'HTTP Request: GET [^\s]+/agent/v1/orders\?[^\s]*host=admin-vps[^\s]* "HTTP/1\.[01] 200', journal))
        assert polls > 0, 'No successful normal service poll observed'
        record('verified.json', {'at': datetime.now(UTC).isoformat(), 'agent': stable,
                                 'gitTransport': git_checks(new_config, mirror, clean, username, token),
                                 'successfulNaturalPollLogEntries': polls,
                                 'oldPasswordRejected': True, 'newPasswordAccepted': True,
                                 'agentTokenScope': ['read:repository'], 'giteaVersion': '1.22.6',
                                 'noClaimEndpointManuallyCalled': True, 'githubWrites': False,
                                 'remoteGitPushes': False, 'secretValuesInEvidence': False})
        phase('rotation-verified')


if __name__ == '__main__':
    try:
        assert sys.argv[1:] in ([], ['--resume-agent-rollback'])
        main(resume=bool(sys.argv[1:]))
    except Exception as error:
        print(json.dumps({'phase': STEP, 'failed': True, 'errorType': type(error).__name__}), flush=True)
        raise SystemExit(1) from None
