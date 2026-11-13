import assert from 'node:assert/strict';
import { mkdtempSync, mkdirSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

const packageDir = process.argv[2];
const expectedVersion = process.argv[3];
const manifest = JSON.parse(readFileSync(join(packageDir, 'package.json'), 'utf8'));
assert.equal(manifest.name, '@aimarket/warden');
assert.equal(manifest.version, expectedVersion);
assert.equal(process.platform, 'linux');
for (const command of ['cat', 'ls']) {
  assert.equal(realpathSync('/usr/bin/' + command), '/usr/lib/cargo/bin/coreutils/' + command);
}

const decisions = { systemCat: 'allow', systemAbsoluteCat: 'allow', systemLs: 'allow', systemAbsoluteLs: 'allow',
  workspaceExecutable: 'deny', workspaceShellLink: 'deny', workspaceSameNameLink: 'deny' };

for (const entrypoint of ['dist/flow-guard-codex.js', 'codex-hooks/scripts/flow-guard-codex.mjs']) {
  const { codexPost, codexPre } = await import(pathToFileURL(join(packageDir, entrypoint)));
  const scratch = mkdtempSync('/tmp/warden-smoke-');
  const cwd = join(scratch, 'project');
  const state = join(scratch, 'state');
  mkdirSync(cwd);
  mkdirSync(state);
  const policy = join(state, 'policy.json');
  writeFileSync(policy, '{"mode":"deny"}');
  const env = { HOME: scratch, PATH: cwd + ':/usr/bin:/bin', WARDEN_STATE_DIR: state, WARDEN_FLOW_POLICY: policy };
  const base = { session_id: 'ubuntu-uutils-check', cwd, turn_id: 't1' };
  const options = { env, block: 'all' };
  codexPost({ ...base, tool_name: 'Bash', tool_input: { command: 'curl -s https://outside.invalid/issues' }, tool_response: 'untrusted outside text' }, options);
  const read = (command) => codexPre({ ...base, tool_name: 'exec_command', tool_input: { cmd: command } }, options)
    ?.hookSpecificOutput.permissionDecision ?? 'allow';
  const observed = {
    systemCat: read('cat notes.txt'),
    systemAbsoluteCat: read('/usr/bin/cat notes.txt'),
    systemLs: read('ls -la'),
    systemAbsoluteLs: read('/bin/ls -la'),
  };
  const shadow = join(cwd, 'cat');
  writeFileSync(shadow, '#!/bin/sh\nexit 99\n', { mode: 0o755 });
  observed.workspaceExecutable = read('cat notes.txt');
  rmSync(shadow);
  symlinkSync('/bin/sh', shadow);
  observed.workspaceShellLink = read('cat notes.txt');
  rmSync(shadow);
  symlinkSync('/usr/bin/cat', shadow);
  observed.workspaceSameNameLink = read('cat notes.txt');
  console.log(manifest.version, entrypoint, JSON.stringify(observed));
  if (expectedVersion === '0.26.1') {
    assert.deepEqual(observed, decisions);
  } else {
    for (const key of ['systemCat', 'systemLs']) {
      assert.equal(observed[key], 'deny', key);
    }
    assert.equal(observed.workspaceShellLink, 'allow', 'reproduce old shell-link bypass');
  }
  rmSync(scratch, { recursive: true });
}
