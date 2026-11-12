import { pathToFileURL } from 'node:url';
import { getStatus } from './http.mjs';

export const JOB = 'platform_smoke';
const PROXY = Object.freeze({ hostname: 'egress', port: 8888 });
const CHECKS = Object.freeze([
  Object.freeze({ name: 'backend_health', request: Object.freeze({ hostname: 'backend', port: 8080, path: '/health', timeoutMs: 3000 }) }),
  Object.freeze({ name: 'modelmarket_https', request: Object.freeze({ hostname: 'modelmarket.dev', port: 443, path: '/', secure: true, proxy: PROXY, timeoutMs: 3000 }) }),
  Object.freeze({ name: 'hub_https', request: Object.freeze({ hostname: 'hub.attestedmemory.net', port: 443, path: '/', secure: true, proxy: PROXY, timeoutMs: 3000 }) }),
]);

/** The broker's env -i is the primary boundary; unexpected credential/TLS overrides fail before networking. */
export function safeEnvironment(environment) {
  return !Object.keys(environment).some(name => /TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|API.?KEY|ACCESS.?KEY|PRIVATE.?KEY|^DATABASE_URL$|^REDIS_URL$/i.test(name)
    || ['NODE_OPTIONS', 'NODE_TLS_REJECT_UNAUTHORIZED', 'NODE_EXTRA_CA_CERTS', 'SSL_CERT_FILE', 'SSL_CERT_DIR'].includes(name.toUpperCase()));
}

export async function runSmoke(probe = getStatus, environment = process.env, args = []) {
  const enabled = args.length === 0 && safeEnvironment(environment);
  const checks = await Promise.all(CHECKS.map(async check => {
    let status = 0;
    if (enabled) {
      try {
        const value = await probe(check.request);
        if (Number.isInteger(value) && value >= 100 && value <= 599) status = value;
      } catch { /* A generic failure status retains no remote error/header/body. */ }
    }
    return { name: check.name, pass: status === 200, status };
  }));
  return { job: JOB, checks, passed: checks.every(check => check.pass) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const result = await runSmoke(getStatus, process.env, process.argv.slice(2));
  process.stdout.write(JSON.stringify(result) + '\n');
  process.exitCode = result.passed ? 0 : 1;
}
