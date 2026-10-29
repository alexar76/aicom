// Read-only reproduction of the component test's relative-link check.
import { existsSync, readFileSync } from 'node:fs';
import { dirname, isAbsolute, relative, resolve } from 'node:path';

const root = resolve(process.argv[2] ?? 'warden');
const readmes = ['', '-ru', '-es', '-fr', '-zh'].map(suffix => `README${suffix}.md`);
const docs = ['gates', 'threat-feed', 'integration', 'mcp-survey', 'security-hardening', 'scan', 'scanner-comparison', 'flow-guard']
  .flatMap(name => ['', '.ru', '.es', '.fr', '.zh'].map(suffix => `docs/${name}${suffix}.md`));
const externalReferences = [], brokenLinks = [];
let checkedLinks = 0;
for (const file of [...readmes, ...docs]) {
  const text = readFileSync(resolve(root, file), 'utf8');
  for (const match of text.matchAll(/\]\(([^)#\s]+)(?:#[^)\s]*)?\)/g)) {
    const target = match[1];
    if (/^(https?:|mailto:)/.test(target)) continue;
    const destination = resolve(root, dirname(file), target);
    const local = relative(root, destination);
    const outsideWarden = local === '..' || local.startsWith('../') || isAbsolute(local);
    const row = { file, target, exists: existsSync(destination) };
    if (outsideWarden) externalReferences.push(row);
    if (!row.exists) brokenLinks.push(row);
    checkedLinks++;
  }
}
const requiredWorkspaceFiles = [...new Set(externalReferences.map(row =>
  relative(resolve(root, '..'), resolve(root, dirname(row.file), row.target))))].sort();
console.log(JSON.stringify({
  documentsChecked: readmes.length + docs.length, checkedLinks,
  brokenLinkCount: brokenLinks.length, brokenLinks,
  outsideWardenCount: externalReferences.length, externalReferences,
  requiredWorkspaceFiles,
}, null, 2));
if (brokenLinks.length) process.exitCode = 1;
