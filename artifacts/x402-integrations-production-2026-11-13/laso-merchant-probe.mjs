import { readFileSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";
import { privateKeyToAccount } from "../../argus/node_modules/viem/_esm/accounts/index.js";
import { createSiweMessage } from "../../argus/node_modules/viem/_esm/siwe/index.js";

const origin = "https://laso.finance";
const authUrl = `${origin}/auth`;
const chainId = "eip155:8453";
const keyFile = join(homedir(), ".aicom-pov-buyer.json");
if (statSync(keyFile).mode & 0o077) throw new Error("Expected an owner-only test wallet file");
const { private_key: key } = JSON.parse(readFileSync(keyFile, "utf8"));
const account = privateKeyToAccount(key.startsWith("0x") ? key : `0x${key}`);
if (account.address.toLowerCase() !== "0x097e3f339d0b023605e12a6b81e2d6cb7571475a") throw new Error("Unexpected buyer");

const options = () => ({ redirect: "error", signal: AbortSignal.timeout(12000) });
const initial = await fetch(authUrl, options());
const header = initial.headers.get("payment-required");
if (initial.status !== 402 || !header) throw new Error("Laso did not return an authentication challenge");
const challenge = JSON.parse(Buffer.from(header, "base64")).extensions?.["sign-in-with-x"];
await initial.body?.cancel();
const { domain, uri, statement, version, nonce, issuedAt, expirationTime, resources } = challenge.info;
if (domain !== "laso.finance" || uri !== authUrl || statement !== "Sign in to Laso Finance" || version !== "1"
    || resources?.length !== 1 || resources[0] !== authUrl || !challenge.supportedChains.some((c) => c.chainId === chainId && c.type === "eip191")) {
  throw new Error("Laso authentication challenge is not bound to the expected route");
}
const claims = { domain, address: account.address, uri, statement, version, nonce, issuedAt, expirationTime, resources, chainId, type: "eip191" };
const message = createSiweMessage({ ...claims, chainId: 8453, issuedAt: new Date(issuedAt), expirationTime: new Date(expirationTime) });
const signature = await account.signMessage({ message });
const auth = await fetch(authUrl, { ...options(), headers: { "SIGN-IN-WITH-X": Buffer.from(JSON.stringify({ ...claims, signature })).toString("base64") } });
if (auth.status !== 200) throw new Error(`Laso authentication returned HTTP ${auth.status}`);
const authenticated = await auth.json();
if (authenticated.user_id?.toLowerCase() !== account.address.toLowerCase() || !authenticated.auth?.id_token) throw new Error("Laso authenticated a different wallet");

const merchants = [];
for (const name of ["Uber", "Amazon"]) {
  const result = await fetch(`${origin}/search-merchants?${new URLSearchParams({ q: name })}`, {
    ...options(), headers: { authorization: `Bearer ${authenticated.auth.id_token}`, accept: "application/json" },
  });
  const payload = result.ok ? await result.json() : {};
  merchants.push({ name, http_status: result.status, matches: (payload.merchants ?? []).map(({ name, status }) => ({ name, status })) });
}
console.log(JSON.stringify({ auth_status: auth.status, payer: account.address, token_ttl_seconds: Number(authenticated.auth.expires_in), merchants, paid: false }, null, 2));
