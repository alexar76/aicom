const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '../..');
const proof = { legacyMinimatch: [], patchedMinimatch: [], glob: [], consumers: [] };
const projects = JSON.parse(fs.readFileSync(path.join(__dirname, 'npm-projects.json')));

async function main() {
  for (const project of [...projects, 'contracts/zk']) {
    const lock = JSON.parse(fs.readFileSync(path.join(root, project, 'package-lock.json')));
    for (const [pkgPath, meta] of Object.entries(lock.packages)) {
      if (!pkgPath.endsWith('/minimatch')) continue;
      const pkgDir = path.join(root, project, pkgPath);
      const req = createRequire(path.join(pkgDir, 'package.json'));
      const installed = JSON.parse(fs.readFileSync(path.join(pkgDir, 'package.json')));
      assert.equal(installed.version, meta.version);
      const entry = req.resolve(pkgDir);
      const source = fs.readFileSync(entry);
      const mm = req(pkgDir);
      const pattern = Array(12).fill('**/../a/b').join('/');
      const start = performance.now();
      const m = new mm.Minimatch(pattern, { optimizationLevel: 2, braceExpandMax: 32 });
      assert(mm.Minimatch);
      assert(new mm.Minimatch('**/*.ts').match('src/nested/file.ts'));
      assert(!new mm.Minimatch('**/*.ts').match('src/file.js'));
      const row = { project, path: pkgPath, version: installed.version,
        source_sha256: crypto.createHash('sha256').update(source).digest('hex'),
        firstPhasePreProcess: typeof mm.Minimatch.prototype.firstPhasePreProcess,
        pattern_count: m.globParts.length, milliseconds: performance.now() - start };
      if (/^[35]\./.test(installed.version)) {
        assert.equal(typeof mm, 'function'); // Legacy consumers require a callable export.
        assert.equal(row.firstPhasePreProcess, 'undefined');
        assert(!source.includes(Buffer.from('optimizationLevel')));
        assert.equal(m.globParts.length, 1);
        proof.legacyMinimatch.push(row);
      } else {
        assert.equal(installed.version, '11.0.1');
        assert(m.globParts.length <= 32);
        proof.patchedMinimatch.push(row);
      }
    }
  }
  for (const project of ['contracts/solana', 'cite-desks/emberline/frontend']) {
    const req = createRequire(path.join(root, project, 'package.json'));
    const glob = req('glob');
    assert.equal(req('glob/package.json').version, '14.0.2');
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'aicom-glob-abort-'));
    try {
      for (let i = 0; i < 12; i++) {
        fs.mkdirSync(path.join(dir, String(i), 'nested'), { recursive: true });
        fs.writeFileSync(path.join(dir, String(i), 'nested', 'file.txt'), 'fixture');
      }
      const ctl = new AbortController();
      let reads = 0;
      const countingFs = { ...fs, readdir(...args) {
        reads++;
        if (reads === 1) ctl.abort(new Error('test-abort'));
        return fs.readdir(...args);
      }};
      await assert.rejects(glob.glob('**/*', { cwd: dir, signal: ctl.signal, fs: countingFs }), /test-abort/);
      const atReject = reads;
      await new Promise(resolve => setTimeout(resolve, 30));
      assert.equal(reads, atReject);
      assert.equal(reads, 1);
      assert.equal((await glob.glob('**/*.txt', { cwd: dir })).length, 12);
      proof.glob.push({ project, version: '14.0.2', reads, readsAfterReject: reads - atReject, ordinaryMatches: 12 });
    } finally { fs.rmSync(dir, { recursive: true, force: true }); }
  }
  for (const project of ['aimarket-sdks/typescript', 'web/frontend', 'pingblip/web', 'pingblip/memeforge']) {
    const req = createRequire(path.join(root, project, 'package.json'));
    const { ESLint } = req('eslint');
    const eslint = new ESLint({ cwd: path.join(root, project), overrideConfigFile: true,
      overrideConfig: [{ files: ['**/*.js'], rules: { 'no-unused-vars': 'error' } }] });
    const results = await eslint.lintText('const unused = 1;', { filePath: 'src/security-fixture.js' });
    assert(results[0].messages.some(m => m.ruleId === 'no-unused-vars'));
    proof.consumers.push({ project, eslint: 'file-pattern dispatch and lint pass' });
  }
  for (const project of ['independent/kova-gateway', 'independent/verified-execution-hub']) {
    const req = createRequire(path.join(root, project, 'package.json'));
    const { Project } = req('ts-morph');
    const p = new Project({ useInMemoryFileSystem: true });
    p.createSourceFile('/src/example.ts', 'export const x = 1;');
    assert.equal(p.getSourceFiles('**/*.ts').length, 1);
    assert.equal(p.getSourceFiles('**/*.js').length, 0);
    proof.consumers.push({ project, tsMorph: 'glob source selection pass' });
  }
  fs.writeFileSync(path.join(__dirname, 'dependency-regressions.json'), JSON.stringify(proof, null, 2) + '\n');
  console.log(JSON.stringify(proof, null, 2));
}
main().catch(error => { console.error(error); process.exitCode = 1; });
