import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { buildPoseidon } from '@aimarket/circomlibjs-poseidon';

const fixture = JSON.parse(readFileSync(new URL('./fixtures/poseidon-circomlibjs-0.1.7.json', import.meta.url)));
const vendor = new URL('../vendor/circomlibjs-poseidon/', import.meta.url);
const helper = fileURLToPath(new URL('../scripts/poseidon2.mjs', import.meta.url));

test('Poseidon WASM implementation and constants retain their upstream bytes', () => {
  const provenance = JSON.parse(readFileSync(new URL('UPSTREAM.json', vendor)));
  for (const [path, expected] of Object.entries(provenance.files)) {
    assert.equal(createHash('sha256').update(readFileSync(new URL(path, vendor))).digest('hex'), expected, path);
  }
});

test('Poseidon agrees with frozen pre-migration commitments and nullifiers', async () => {
  const poseidon = await buildPoseidon();
  assert.equal(fixture.vectors.length, 72);
  for (const { inputs, output } of fixture.vectors) {
    assert.equal(poseidon.F.toString(poseidon(inputs.map(BigInt))), output, inputs.join(','));
  }
  assert.equal(fixture.vectors[1].output, '7853200120776062878684798364095072458815029376092732009249414926327459813530');
});

test('witness CLI keeps decimal stdout and rejects malformed arguments', () => {
  const valid = spawnSync(process.execPath, [helper, '1', '2'], { encoding: 'utf8' });
  assert.equal(valid.status, 0, valid.stderr);
  assert.equal(valid.stdout, fixture.vectors[1].output);
  assert.equal(valid.stderr, '');
  for (const args of [[], ['1'], ['1', '2', '3'], ['malformed', '2']]) {
    const invalid = spawnSync(process.execPath, [helper, ...args], { encoding: 'utf8' });
    assert.notEqual(invalid.status, 0);
    assert.equal(invalid.stdout, '');
  }
});

test('private witnesses use bounded stdin without changing commitments', () => {
  const valid = spawnSync(process.execPath, [helper, '--stdin'], {
    input: JSON.stringify(['1', '2']), encoding: 'utf8',
  });
  assert.equal(valid.status, 0, valid.stderr);
  assert.equal(valid.stdout, fixture.vectors[1].output);
  for (const input of ['{', '[1,2]', '["1"]', JSON.stringify(['1'.repeat(5000), '2'])]) {
    const invalid = spawnSync(process.execPath, [helper, '--stdin'], { input, encoding: 'utf8' });
    assert.notEqual(invalid.status, 0);
    assert.equal(invalid.stdout, '');
    assert.ok(!invalid.stderr.includes(input));
  }
});
