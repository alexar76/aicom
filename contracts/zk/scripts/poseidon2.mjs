#!/usr/bin/env node
/** Poseidon(2) over BN254 — matches circomlib (input_validity circuit); original circomlibjs WASM. */
import { buildPoseidon } from "@aimarket/circomlibjs-poseidon";

let args = process.argv.slice(2);
try {
  // The hub hashes private witnesses. Keep them out of process listings while
  // retaining the two-argument interface for existing operator tooling.
  if (args.length === 1 && args[0] === '--stdin') {
    let input = '';
    for await (const chunk of process.stdin) {
      input += chunk.toString('utf8');
      if (Buffer.byteLength(input) > 4096) throw new Error('input too large');
    }
    args = JSON.parse(input);
  }
  if (!Array.isArray(args) || args.length !== 2 ||
      !args.every(value => typeof value === 'string')) {
    throw new Error('expected two field elements');
  }
  const poseidon = await buildPoseidon();
  process.stdout.write(poseidon.F.toString(poseidon(args.map(BigInt))));
} catch {
  console.error('usage: poseidon2.mjs <field_a> <field_b> OR --stdin (JSON string pair, at most 4096 bytes)');
  process.exitCode = 1;
}
