#!/usr/bin/env node
/** Poseidon(2) over BN254 — matches circomlib/circomlibjs (input_validity circuit). */
import { buildPoseidon } from "circomlibjs";

const poseidon = await buildPoseidon();
const F = poseidon.F;
const args = process.argv.slice(2);
if (args.length !== 2) {
  console.error("usage: poseidon2.mjs <field_a> <field_b>");
  process.exit(1);
}
const a = BigInt(args[0]);
const b = BigInt(args[1]);
process.stdout.write(F.toString(poseidon([a, b])));
