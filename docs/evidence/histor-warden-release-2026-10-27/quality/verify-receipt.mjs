// Verifies evidence without changing the production-only npm publication gate.
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { buildDigest, checkEvidence } from '../../../../warden/scripts/check-quality-gate.mjs';

const envelopePath = process.argv[2];
if (!envelopePath) throw Error('Usage: node verify-receipt.mjs ENVELOPE_JSON [WARDEN_BUILD]');
const build = process.argv[3] || fileURLToPath(new URL('../../../../warden/', import.meta.url));
const key = readFileSync(new URL('../../../../warden/scripts/quality-public-key.pem', import.meta.url));
try {
  const report = checkEvidence(JSON.parse(readFileSync(envelopePath, 'utf8')), key, buildDigest(build));
  console.log(JSON.stringify(report, null, 2));
} catch (error) {
  console.error(`Receipt verification failed: ${error.message}`);
  process.exitCode = 1;
}
