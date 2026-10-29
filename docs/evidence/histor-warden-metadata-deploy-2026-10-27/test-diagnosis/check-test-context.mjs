// Static context-closure proof; actual Docker/Vitest execution is recorded separately.
import { readFileSync, existsSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { resolve } from 'node:path';

const diagnosis = JSON.parse(readFileSync(new URL('./full-workspace-links.json', import.meta.url), 'utf8'));
const expected = [
  'docs/growth/kevin-annotations-answer-review-2026-10-25.ru.md',
  'docs/growth/launchgate-methodology-2026-10-25.ru.md',
  'docs/growth/launchgate-selection-2026-10-25.en.md',
  'docs/growth/launchgate-selection-2026-10-25.ru.md',
  'docs/growth/launchgate-tie-selection-2026-10-25.en.md',
  'docs/growth/launchgate-tie-selection-2026-10-25.ru.md',
  'docs/growth/warden-thresholds-2026-10-25.ru.md',
];
const assert = (condition, message) => { if (!condition) throw Error(message); };
assert(JSON.stringify(diagnosis.requiredWorkspaceFiles) === JSON.stringify(expected), 'Reference closure changed');
assert(diagnosis.outsideWardenCount === 22 && diagnosis.brokenLinkCount === 0, 'Unexpected original document state');
const tracked = new Set(execFileSync('git', ['ls-files', '-z', '--', ...expected], { encoding: 'utf8' }).split('\0'));
const ignores = ['.dockerignore', 'warden/deploy/Dockerfile.histor.dockerignore'];
for (const file of ignores) {
  const text = readFileSync(file, 'utf8');
  const exceptions = text.split(/\r?\n/).filter(line => line.startsWith('!docs/growth/') && line.endsWith('.md')).map(line => line.slice(1)).sort();
  assert(JSON.stringify(exceptions) === JSON.stringify(expected), `${file} must expose exactly the required seven documents`);
}
const recipe = readFileSync('warden/deploy/Dockerfile.histor', 'utf8');
for (const file of expected) {
  assert(tracked.has(file) && existsSync(resolve(file)), 'A required test input is not committed');
  assert(recipe.includes(file), 'Recipe must copy every required public document');
}
const finalStage = recipe.split('FROM histor:warden-remediation-base\n')[1];
assert(finalStage && !finalStage.includes('/docs/growth'), 'Public reference documents must not enter the final image');
const finalCopies = [...finalStage.matchAll(/^COPY --from=test (.+)$/gm)].map(match => match[1]);
assert(JSON.stringify(finalCopies) === JSON.stringify([
  '/warden/dist /app/scanner/node_modules/@aimarket/warden/dist',
  '/warden/package.json /app/scanner/node_modules/@aimarket/warden/package.json',
  '/warden/src /opt/warden-source/src',
]), 'Final-stage payload changed');
console.log(JSON.stringify({
  kind: 'static-context-closure-proof', documentsChecked: diagnosis.documentsChecked,
  checkedLinks: diagnosis.checkedLinks, missingBefore: diagnosis.outsideWardenCount,
  missingWithRequiredTestInputs: 0, requiredWorkspaceFiles: expected,
  ignoreFiles: ignores, recipeSha256: createHash('sha256').update(recipe).digest('hex'),
  finalStageCopies: finalCopies, finalImageReferenceDocuments: 0,
  assertionsChanged: false, runtimeChanged: false,
}, null, 2));
