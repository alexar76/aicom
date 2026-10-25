import { createRequire } from 'node:module';
import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { ESLint } from 'eslint';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

// Test the actual Next plugin consumer, including its scoped npm override.
const require = createRequire(import.meta.url);
const pluginRequire = createRequire(require.resolve('@next/eslint-plugin-next/package.json'));
const { getRootDirs } = pluginRequire('./dist/utils/get-root-dirs.js');

describe('Next lint root-directory glob compatibility', () => {
  let root: string;
  beforeEach(() => {
    root = mkdtempSync(join(tmpdir(), 'aicom-next-glob-'));
    for (const name of ['one', 'two']) mkdirSync(join(root, 'apps', name), { recursive: true });
    writeFileSync(join(root, 'apps', 'not-a-directory.txt'), 'fixture');
  });
  afterEach(() => rmSync(root, { recursive: true, force: true }));

  it('resolves tinyglobby rather than the braces dependency tree', () => {
    const metadata = pluginRequire('fast-glob/package.json');
    expect(metadata.name).toBe('tinyglobby');
    expect(metadata.version).toBe('0.2.17');
    expect(typeof pluginRequire('fast-glob').globSync).toBe('function');
  });

  it('preserves the default project root', () => {
    expect(getRootDirs({ cwd: root, settings: {} })).toEqual([root]);
  });

  it('expands directory globs without accepting matching files', () => {
    expect(getRootDirs({ cwd: root, settings: { next: { rootDir: `${root}/apps/*` } } }).map((p: string) => resolve(p)).sort())
      .toEqual([join(root, 'apps', 'one'), join(root, 'apps', 'two')]);
  });

  it('supports brace patterns and arrays in the actual Next utility', () => {
    expect(getRootDirs({ cwd: root, settings: { next: { rootDir: [`${root}/apps/{one,two}`, 42] } } }).map((p: string) => resolve(p)).sort())
      .toEqual([join(root, 'apps', 'one'), join(root, 'apps', 'two')]);
  });

  it('normalizes Windows separators before expanding a configured root', () => {
    expect(getRootDirs({ cwd: root, settings: { next: { rootDir: `${root}/apps/one`.replaceAll('/', '\\') } } }).map((p: string) => resolve(p)))
      .toEqual([join(root, 'apps', 'one')]);
  });

  it.each(['literal', 'glob', 'brace', 'array'])('keeps the actual Next navigation rule active for %s roots', async (form) => {
    const pages = join(root, 'apps', 'one', 'pages');
    mkdirSync(pages);
    writeFileSync(join(pages, 'about.js'), 'export default function About() {}');
    const pattern = { literal: `${root}/apps/one`, glob: `${root}/apps/*`,
      brace: `${root}/apps/{one,two}`, array: [`${root}/apps/one`] }[form];
    const lint = new ESLint({ cwd: root, overrideConfigFile: true, overrideConfig: [{
      files: ['**/*.js'], languageOptions: { parserOptions: { ecmaFeatures: { jsx: true } } },
      plugins: { '@next/next': require('@next/eslint-plugin-next') },
      settings: { next: { rootDir: pattern } },
      rules: { '@next/next/no-html-link-for-pages': 'error' },
    }] });
    const [result] = await lint.lintText('const link = <a href="/about">About</a>;', { filePath: join(root, 'consumer.js') });
    expect(result.messages.map((m) => m.ruleId)).toContain('@next/next/no-html-link-for-pages');
    expect(result.fatalErrorCount).toBe(0);
  });
});
