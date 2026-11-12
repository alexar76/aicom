import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

test('rendered worker has no credentials, mounts, host namespaces or broad network', async t => {
  let result;
  try {
    result = await promisify(execFile)('docker', ['compose', '-f', fileURLToPath(new URL('../../worker.compose.yaml', import.meta.url)), 'config', '--format', 'json'], {
      env: { PATH: process.env.PATH, QA_WORKER_DIR: fileURLToPath(new URL('..', import.meta.url)), QA_WORKER_IMAGE: 'aicom-qa-worker:test', QA_NODE_IMAGE: 'node:22.23.4-bookworm-slim@sha256:5ec23b7c622b00547753bc6ffd78085dd868a68aeb41c8e0a1418f033e13d96d', GITHUB_TOKEN: 'synthetic-host-secret-never-forward' },
      timeout: 10000,
    });
  } catch (error) {
    if (error.code === 'ENOENT') { t.skip('Docker Compose CLI unavailable'); return; }
    throw error;
  }
  const config = JSON.parse(result.stdout);
  const worker = config.services['qa-worker'];
  assert.equal(worker.user, '10001:10001');
  assert.equal(worker.read_only, true);
  assert.deepEqual(worker.cap_drop, ['ALL']);
  assert.equal(Boolean(worker.privileged), false);
  assert.deepEqual(worker.cap_add ?? [], []);
  assert.equal(worker.restart, 'no');
  assert.equal(Number(worker.mem_limit), 134217728);
  assert.equal(worker.pids_limit, 64);
  assert.deepEqual(worker.tmpfs, ['/tmp:mode=1777,size=32m,noexec,nosuid,nodev']);
  assert.deepEqual(worker.dns, ['127.0.0.1']);
  assert.equal(worker.sysctls['net.ipv6.conf.all.disable_ipv6'], '1');
  assert.ok(worker.security_opt.includes('no-new-privileges:true'));
  for (const name of ['volumes', 'env_file', 'environment', 'secrets', 'ports', 'network_mode', 'pid', 'devices', 'use_api_socket']) {
    assert.equal(worker[name], undefined, `unexpected ${name}`);
  }
  assert.deepEqual(Object.keys(worker.networks), ['qa_agent']);
  assert.equal(worker.networks.qa_agent.ipv4_address, '10.250.0.5');
  assert.equal(config.networks.qa_agent.name, 'multica_agent');
  assert.equal(config.networks.qa_agent.external, true);
  assert.doesNotMatch(result.stdout, /synthetic-host-secret-never-forward|GITHUB_TOKEN/);
});

test('image copies only fixed source, has no runtime install, and pins the verified official base digest', async () => {
  const dockerfile = await readFile(new URL('../Dockerfile', import.meta.url), 'utf8');
  assert.match(dockerfile, /ARG NODE_IMAGE=node:22\.23\.4-bookworm-slim@sha256:[0-9a-f]{64}/);
  assert.match(dockerfile, /COPY --chown=0:0 package\.json http\.mjs smoke\.mjs idle\.mjs \/opt\/qa\//);
  assert.doesNotMatch(dockerfile, /npm (?:install|ci)|apt-get|COPY \. /);
  assert.match(dockerfile, /USER 10001:10001/);
  const ignore = await readFile(new URL('../.dockerignore', import.meta.url), 'utf8');
  assert.ok(ignore.startsWith('**\n'));
});
