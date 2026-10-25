import { mkdir, copyFile, readFile, writeFile, mkdtemp, rm } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { createHash } from "node:crypto";

const root = fileURLToPath(new URL("../../", import.meta.url));
const core = path.join(root, "security/vendor/x402-core");
const check = process.argv.includes("--check");
execFileSync("npm", ["run", "build"], { cwd: core, stdio: "inherit" });
const output = path.join(root, "security/vendor/archives");
await mkdir(output, { recursive: true });
async function pack(dir, consumers) {
  const packed = JSON.parse(execFileSync("npm", ["pack", "--ignore-scripts", "--json", "--cache", path.join(tmpdir(), "aimarket-vendor-npm-cache"), "--pack-destination", output], { cwd: dir, encoding: "utf8" }));
  const filename = packed[0].filename;
  for (const consumer of consumers) {
    const destination = path.join(root, consumer, "vendor");
    if (check) {
      const [expected, actual] = await Promise.all([readFile(path.join(output, filename)), readFile(path.join(destination, filename))]);
      if (!expected.equals(actual)) throw new Error(`Vendor archive differs from its source: ${consumer}/vendor/${filename}. Run node security/vendor/build.mjs.`);
      const lock = JSON.parse(await readFile(path.join(root, consumer, "package-lock.json"), "utf8"));
      if (lock.packages[`node_modules/${packed[0].name}`]?.integrity !== packed[0].integrity) throw new Error(`Lockfile archive integrity is stale: ${consumer}/${packed[0].name}`);
    } else {
      await mkdir(destination, { recursive: true });
      await copyFile(path.join(output, filename), path.join(destination, filename));
    }
  }
  if (check && packed[0].name !== "@aimarket/x402-cdp") {
    const lock = JSON.parse(await readFile(path.join(root, "security/vendor/package-lock.json"), "utf8"));
    if (lock.packages[`node_modules/${packed[0].name}`]?.integrity !== packed[0].integrity) throw new Error(`Validation harness archive integrity is stale: ${packed[0].name}`);
  }
  process.stdout.write(`${filename}: ${packed[0].integrity}\n`);
}
const all = ["argus", "domain-kit", "esim-kit/rails", "esim-kit/store", "okx-a2mcp", "scripts/delivery-survey"];
const sellers = ["domain-kit", "esim-kit/rails", "esim-kit/store", "okx-a2mcp"];
await pack(core, all);
await pack(path.join(root, "security/vendor/x402-cdp"), sellers);

// These two SDKs already use APIs compatible with Zod 4 (covered by signature,
// SIWx and CDP differential tests). Their original dependency range still names
// Zod 3. Change metadata explicitly instead of making npm ignore the range.
const upstream = path.join(root, "security/vendor/upstream");
for (const original of JSON.parse(await readFile(path.join(upstream, "provenance.json"), "utf8"))) {
  const archive = path.join(upstream, original.filename);
  const integrity = `sha512-${createHash("sha512").update(await readFile(archive)).digest("base64")}`;
  if (integrity !== original.integrity) throw new Error(`Upstream archive integrity mismatch: ${original.name}`);
  const temporary = await mkdtemp(path.join(tmpdir(), "aimarket-x402-metadata-"));
  try {
    execFileSync("tar", ["-xzf", archive, "-C", temporary]);
    const dir = path.join(temporary, "package"), manifest = path.join(dir, "package.json");
    const metadata = JSON.parse(await readFile(manifest, "utf8"));
    metadata.version = "2.28.0+aimarket.zod4.1";
    metadata.dependencies.zod = "4.6.7";
    delete metadata.devDependencies;
    delete metadata.scripts;
    metadata.files = ["dist", "LICENSE", "UPSTREAM.md"];
    await writeFile(manifest, JSON.stringify(metadata, null, 2) + "\n");
    await copyFile(path.join(core, "LICENSE"), path.join(dir, "LICENSE"));
    if (original.name === "@x402/extensions") {
      const generated = path.join(temporary, "declarations");
      execFileSync(process.execPath, [path.join(core, "node_modules/typescript/bin/tsc"), "--declaration", "--emitDeclarationOnly", "--skipLibCheck", "false", "--target", "ES2022", "--module", "NodeNext", "--moduleResolution", "NodeNext", "--types", "node", "--typeRoots", path.join(core, "node_modules/@types"), "--outDir", generated, path.join(core, "extensions-siwx-schema.ts")]);
      const schema = (await readFile(path.join(generated, "extensions-siwx-schema.d.ts"), "utf8")).match(/export declare const SIWxPayloadSchema:[\s\S]*;/)?.[0].replace(/^export /, "");
      if (!schema) throw new Error("Zod 4 SIWx declaration generation failed");
      for (const target of ["dist/esm/sign-in-with-x/index.d.mts", "dist/cjs/sign-in-with-x/index.d.ts"]) {
        const file = path.join(dir, target), text = await readFile(file, "utf8");
        const start = text.indexOf("declare const SIWxPayloadSchema:"), type = text.indexOf("type SIWxPayload =", start);
        const end = text.lastIndexOf(";", type) + 1;
        if (start < 0 || type < 0 || end <= start) throw new Error(`SIWx declaration patch did not apply: ${target}`);
        const migrated = text.slice(0, start) + schema + text.slice(end);
        await writeFile(file, migrated);
      }
    }
    await writeFile(path.join(dir, "UPSTREAM.md"), `# Local Zod migration\n\nOriginal: ${original.name}@${original.version}\n\nRegistry integrity: ${original.integrity}\n\nRepository: https://github.com/x402-foundation/x402\n\nEvery original runtime and source-map byte is retained. Package metadata migrates the compatible Zod APIs to Zod 4.6.7 and adds the transparent local version suffix. The extensions SIWx schema declarations are regenerated for Zod 4 in both ESM/CJS formats; the matching runtime schema is unchanged. Build-time development dependencies/scripts are omitted from this runtime archive. Apache-2.0 license retained. Rebuild with security/vendor/build.mjs and verify with --check.\n`);
    await pack(dir, original.name === "@x402/evm" ? all : sellers);
  } finally { await rm(temporary, { recursive: true, force: true }); }
}
