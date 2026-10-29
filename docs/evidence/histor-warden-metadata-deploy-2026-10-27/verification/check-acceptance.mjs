// Verifies existing evidence; cannot trigger evaluation, deployment or tool calls.
import { readFileSync, writeFileSync } from 'node:fs';
import { checkEvidence } from '../../../../warden/scripts/check-quality-gate.mjs';

const options = new Map();
for (let i = 2; i < process.argv.length; i += 2) options.set(process.argv[i], process.argv[i + 1]);
for (const key of ['--before', '--remote', '--http', '--candidate', '--live', '--image', '--source', '--output']) {
  if (!options.get(key)) throw Error(`Missing ${key}`);
}
const load = key => JSON.parse(readFileSync(options.get(key), 'utf8'));
const remote = load('--remote');
const before = load('--before');
const http = load('--http');
const image = options.get('--image');
const source = options.get('--source');
if (!/^sha256:[0-9a-f]{64}$/.test(image) || !/^[0-9a-f]{40}$/.test(source)) throw Error('Immutable image and source required');
const digest = '3b6b074cf0be2415a049610d2908787d820b321ae68eb6d4837306dc9f5f16de';
const packageHash = '0411601d6ec47d8d14f608a6643a94589e094940dcd93dde36bdcda52a57a34b';
const key = readFileSync(new URL('../../../../warden/scripts/quality-public-key.pem', import.meta.url));
const candidate = checkEvidence(load('--candidate'), key, digest);
const live = checkEvidence(load('--live'), key, digest);
const checks = [];
const check = (name, passed) => checks.push({ name, passed: Boolean(passed) });
check('running immutable image and source', remote.container.running && remote.container.health === 'healthy'
  && remote.container.imageDigest === image && remote.container.sourceCommit === source);
check('reviewed HISTOR application base retained', remote.pinnedApplicationBase.baseLayersPreserved);
check('HISTOR application source byte-identical to predeployment', remote.historApplication.version === before.historApplication.version
  && remote.historApplication.pythonFiles === before.historApplication.pythonFiles
  && remote.historApplication.sourceSha256 === before.historApplication.sourceSha256);
check('package metadata equals frozen npm package', remote.installedPackage.name === '@aimarket/warden'
  && remote.installedPackage.version === '0.22.2' && remote.installedPackage.packageJsonSha256 === packageHash);
check('package metadata readable by unprivileged runtime', remote.installedPackage.packageJsonMode === '0644'
  && remote.installedPackage.runtimeUid > 0);
check('exact compiled JavaScript', remote.installedPackage.buildDigest === digest && remote.installedPackage.javascriptFiles === 63);
check('scanner runtime describes installed release', remote.scannerDescribe.warden.version === '0.22.2'
  && remote.scannerDescribe.warden.package === '@aimarket/warden@0.22.2'
  && remote.scannerDescribe.patternSet.package === '@aimarket/warden@0.22.2'
  && remote.scannerDescribe.recordSet.package === '@aimarket/warden@0.22.2');
check('MCP runtime version and discovery', remote.mcpDiscovery.serverInfo.name === 'warden'
  && remote.mcpDiscovery.serverInfo.version === '0.22.2' && remote.mcpDiscovery.toolNames.length === 9
  && remote.mcpDiscovery.toolCalls === 0);
check('native accepted source and quality binding', remote.qualityBinding.imageDigest === image
  && remote.qualityBinding.buildDigest === digest && remote.acceptedSource.imageDigest === image
  && remote.acceptedSource.commit === source);
check('signed candidate binds exact image', candidate.phase === 'candidate' && candidate.imageDigest === image);
check('signed live receipt binds exact image and source', live.phase === 'live' && live.imageDigest === image && live.sourceCommit === source);
check('full candidate evaluation retained', candidate.full === true && live.full === true);
for (const [label, health] of [['loopback', remote.loopback.health], ['public', http.health]]) {
  check(`${label} HISTOR production health`, health.httpStatus === 200 && health.ok === true
    && health.service === 'histor' && health.profile === 'prod' && health.store === 'postgresql');
}
check('public route serves pinned application version', remote.loopback.health.version === http.health.version);
check('signed log history preserved', http.logAudit.signature === 'ok'
  && (http.logAudit.consistency === 'unchanged' || /^ok \(/.test(http.logAudit.consistency)));
const storedIssuerMatchesRuntime = remote.loopback.issuer.warden === '@aimarket/warden@0.22.2'
  && http.issuer.warden === '@aimarket/warden@0.22.2';
if (options.get('--require-stored-issuer') === 'true') check('stored issuer metadata registered new release', storedIssuerMatchesRuntime);
const result = {
  verifiedAt: new Date().toISOString(), passed: checks.every(row => row.passed), imageDigest: image, sourceCommit: source,
  warden: { version: remote.installedPackage.version, buildDigest: digest, packageJsonSha256: packageHash },
  historApplicationVersion: http.health.version, historApplication: remote.historApplication,
  logAudit: http.logAudit, candidateRun: candidate.run, liveRun: live.run,
  checks, storedIssuerMatchesRuntime,
  storedIssuerNote: 'Issuer metadata is a stored observation updated by ruleset registration, independently from installed package/runtime metadata.',
  quality: {
    fullEvidence: live.fullEvidence, expiresAt: live.expiresAt,
    suites: Object.fromEntries(Object.entries(live.suites).map(([name, suite]) => [name, { passed: suite.passed, counts: suite.counts }])),
    behaviour: live.behaviour, behaviourSmoke: live.behaviourSmoke,
  },
};
writeFileSync(options.get('--output'), JSON.stringify(result, null, 2) + '\n');
console.log(JSON.stringify({ passed: result.passed, imageDigest: image, sourceCommit: source, storedIssuerMatchesRuntime, checks }, null, 2));
if (!result.passed) process.exitCode = 1;
