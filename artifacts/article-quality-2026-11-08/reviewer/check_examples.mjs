// Offline verification of the article's literal JavaScript examples against the
// historical and current adapters. Scanner output is a fixed synthetic input;
// this does not rerun a model or turn the saved 0/4 sample into a benchmark.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import vm from 'node:vm';

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, '../../..');
const pack = resolve(root, '../PromoMaterials/devto/reviewer-advisory-2026-11-07');
const article = readFileSync(resolve(pack, 'article.md'), 'utf8');
const snippets = [...article.matchAll(/```js\n([\s\S]*?)```/g)].map(match => match[1]);
assert.equal(snippets.length, 2);
const plain = value => JSON.parse(JSON.stringify(value));

const historical = spawnSync('git', ['show', '1ec9bd988:multica/supplier-review/review.mjs'], {
  cwd: root, encoding: 'utf8', maxBuffer: 2_000_000,
});
assert.equal(historical.status, 0, historical.stderr);
const old = await import('data:text/javascript;base64,' + Buffer.from(historical.stdout).toString('base64'));
const current = await import(pathToFileURL(resolve(root, 'multica/supplier-review/review.mjs')).href);

const signal = {
  code: 'TOOL_DEF_IMPERATIVE', severity: 'info', advisory: true,
  gate: 'static-scan', message: 'An informational match on instead of.',
};
const scanner = {
  staticScan: { evaluate: async () => ({ findings: [signal] }) },
  threat: { evaluate: async () => ({ findings: [] }) },
};
const tool = { name: 'translate', description: 'Use Argentine instead of European Spanish.', input_schema: {} };
const server = { id: 'synthetic', name: 'synthetic', url: 'https://example.invalid' };
const fields = finding => ({ check: finding.check, code: finding.code, severity: finding.severity,
  ...(finding.advisory ? { advisory: true } : {}) });
const expectedBefore = fields((await old.wardenFindings(scanner, tool, server))[0]);
const expectedAfter = fields((await current.wardenFindings(scanner, tool, server))[0]);
const example = plain(vm.runInNewContext(snippets[0] + '\n({before, after})'));
assert.deepEqual(example.before, expectedBefore);
assert.deepEqual(example.after, expectedAfter);

const articleFilter = vm.runInNewContext(snippets[1] + '\nletterPoints');
const cases = [
  { code: 'advisory_info', check: 'injection', severity: 'info', advisory: true },
  { code: 'advisory_high', check: 'injection', severity: 'high', advisory: true },
  { code: 'schema_info', check: 'schema', severity: 'info' },
  { code: 'schema_low', check: 'schema', severity: 'low' },
  { code: 'other_low', check: 'endpoint', severity: 'low' },
  { code: 'real_medium', check: 'endpoint', severity: 'medium' },
  { code: 'real_high', check: 'injection', severity: 'high' },
];
assert.deepEqual(plain(articleFilter(cases)), current.letterPoints(cases));
assert.deepEqual(articleFilter(cases).map(item => item.code),
  ['schema_low', 'real_medium', 'real_high']);

const schema = current.schemaProblems({ type: 'string' }, 'input_schema', { input: true });
assert.ok(current.letterPoints(schema).some(item => item.code === 'input_not_object'));
const criticalScanner = {
  staticScan: { evaluate: async () => ({ findings: [{ ...signal, severity: 'critical', advisory: false }] }) },
  threat: scanner.threat,
};
const critical = await current.wardenFindings(criticalScanner, tool, server);
assert.equal(critical[0].severity, 'high');
assert.equal(current.letterPoints(critical).length, 1);

const backup = readFileSync(resolve(pack, 'article.before-quality-2026-11-08.md'), 'utf8');
assert.equal(article.split('---', 3)[1], backup.split('---', 3)[1], 'Frontmatter changed');
const report = {
  status: 'passed', network: 'none', literalJavaScriptBlocksChecked: 2,
  adapterSourceBefore: 'git:1ec9bd988:multica/supplier-review/review.mjs',
  adapterSourceAfter: 'multica/supplier-review/review.mjs',
  before: example.before, after: example.after,
  filterMatrixCases: cases.length,
  eligibleMatrixCodes: articleFilter(cases).map(item => item.code),
  schemaInputControl: 'input_not_object eligible',
  criticalNormalizationControl: 'critical becomes high and remains eligible',
  historicalSample: { date: '2026-11-06', textokit: 0, agentExec: 4, rerun: false,
    scope: 'Recorded checker eligibility counts, not model-draft quality or seller safety' },
  frontmatterPreserved: true,
};
writeFileSync(resolve(here, 'example-checks.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
