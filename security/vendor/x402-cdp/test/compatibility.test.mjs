import test from "node:test";
import assert from "node:assert/strict";
import { generateKeyPairSync } from "node:crypto";
import { pathToFileURL } from "node:url";
import { jwtVerify, importSPKI, decodeJwt } from "jose";
import { privateKeyToAccount } from "viem/accounts";
import { recoverTypedDataAddress } from "viem";
import { x402Client } from "@x402/core/client";
import { PaymentPayloadSchema, PaymentRequiredSchema } from "@x402/core/schemas";
import { ExactEvmScheme, authorizationTypes } from "@x402/evm";
import { SIWxPayloadSchema } from "@x402/extensions/sign-in-with-x";
import { generateCdpJwt, createCdpFacilitatorClient, createX402Server } from "../index.js";

const receiver = `0x${"03".repeat(20)}`;
const buyer = privateKeyToAccount(`0x${"01".repeat(32)}`);
const asset = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913";
const terms = { scheme: "exact", network: "eip155:8453", amount: "12500000", asset, payTo: receiver, maxTimeoutSeconds: 300, extra: { name: "USD Coin", version: "2" } };
const sdkRoot = process.env.CDP_BASELINE_PATH;
const baselineAuth = sdkRoot ? await import(pathToFileURL(`${sdkRoot}/_esm/auth/index.js`)) : null;
const baseline = sdkRoot ? await import(pathToFileURL(`${sdkRoot}/_esm/x402/index.js`)) : null;

for (const type of ["ec", "ed25519"]) {
  test(`${type} CDP authentication verifies with the original key and binds each operation URI`, async () => {
    const pair = generateKeyPairSync(type, type === "ec" ? { namedCurve: "P-256" } : {});
    const jwk = pair.privateKey.export({ format: "jwk" });
    const secret = type === "ec" ? pair.privateKey.export({ type: "pkcs8", format: "pem" })
      : Buffer.concat([Buffer.from(jwk.d, "base64url"), Buffer.from(jwk.x, "base64url")]).toString("base64");
    const key = await importSPKI(pair.publicKey.export({ type: "spki", format: "pem" }), type === "ec" ? "ES256" : "EdDSA");
    const another = generateKeyPairSync(type, type === "ec" ? { namedCurve: "P-256" } : {});
    const wrongKey = await importSPKI(another.publicKey.export({ type: "spki", format: "pem" }), type === "ec" ? "ES256" : "EdDSA");
    for (const operation of ["verify", "settle", "supported"]) {
      const options = { apiKeyId: "disposable-key", apiKeySecret: secret, requestMethod: operation === "supported" ? "GET" : "POST", requestHost: "api.cdp.coinbase.com", requestPath: `/platform/v2/x402/${operation}` };
      const token = await generateCdpJwt(options), verified = await jwtVerify(token, key, { issuer: "cdp", subject: options.apiKeyId });
      assert.deepEqual(verified.payload.uris, [`${options.requestMethod} ${options.requestHost}${options.requestPath}`]);
      assert.equal(verified.payload.exp - verified.payload.iat, 120);
      assert.equal(verified.payload.nbf, verified.payload.iat);
      assert.equal(verified.protectedHeader.kid, options.apiKeyId);
      assert.match(verified.protectedHeader.nonce, /^[a-f0-9]{32}$/);
      await assert.rejects(jwtVerify(token, wrongKey), { code: "ERR_JWS_SIGNATURE_VERIFICATION_FAILED" });
      if (baselineAuth) {
        const original = await jwtVerify(await baselineAuth.generateJwt(options), key);
        for (const field of ["sub", "iss", "uris"]) assert.deepEqual(verified.payload[field], original.payload[field]);
        for (const field of ["alg", "kid", "typ"]) assert.equal(verified.protectedHeader[field], original.protectedHeader[field]);
        assert.equal(original.payload.exp - original.payload.iat, 120);
      }
      const parts = token.split(".");
      parts[1] = Buffer.from(JSON.stringify({ ...verified.payload, uris: ["POST attacker.example/settle"] })).toString("base64url");
      await assert.rejects(jwtVerify(parts.join("."), key));
    }
  });
}

test("escaped PEM newlines fail consistently and base URL endpoint binding matches the SDK", async () => {
  const pair = generateKeyPairSync("ec", { namedCurve: "P-256" });
  const apiKeySecret = pair.privateKey.export({ type: "pkcs8", format: "pem" });
  const options = { apiKeyId: "test", apiKeySecret: apiKeySecret.replaceAll("\n", "\\n"), requestMethod: "POST", requestHost: "example.com", requestPath: "/verify" };
  await assert.rejects(generateCdpJwt(options), /Invalid key format/);
  if (baselineAuth) await assert.rejects(baselineAuth.generateJwt(options), /Invalid key format/);
  for (const suffix of ["/custom", "/custom/", "/custom//", "/custom?region=one", "/custom#fragment"]) {
    const config = { apiKeyId: "test", apiKeySecret, baseUrl: `https://facilitator.example${suffix}` };
    const client = createCdpFacilitatorClient(config), headers = await client._createAuthHeaders();
    const normalized = Object.fromEntries(Object.entries(headers).map(([operation, value]) => [operation, decodeJwt(value.Authorization.slice(7)).uris]));
    if (baseline) {
      const original = baseline.createCdpFacilitatorClient(config), originalHeaders = await original._createAuthHeaders();
      assert.equal(client.url, original.url);
      assert.deepEqual(normalized, Object.fromEntries(Object.entries(originalHeaders).map(([operation, value]) => [operation, decodeJwt(value.Authorization.slice(7)).uris])));
    }
  }
});

test("real EIP-3009 payment bytes survive Zod 4 records, encoding and signer recovery", async () => {
  const client = new x402Client().register(terms.network, new ExactEvmScheme(buyer)).setSpendControls({ maxAmountPerPayment: "20" });
  const required = { x402Version: 2, resource: { url: "https://seller.example/order", description: null, tags: ["esim"] }, accepts: [terms], extensions: { metadata: { nested: { order: "test-order" } } } };
  const parsedRequired = PaymentRequiredSchema.parse(required);
  assert.deepEqual(parsedRequired.accepts, required.accepts);
  assert.equal(parsedRequired.resource.description, undefined);
  assert.deepEqual(parsedRequired.extensions.metadata, required.extensions.metadata);
  const payload = await client.createPaymentPayload(parsedRequired);
  const parsed = PaymentPayloadSchema.parse(JSON.parse(JSON.stringify(payload)));
  assert.deepEqual(parsed.payload, payload.payload);
  const recovered = await recoverTypedDataAddress({ domain: { name: "USD Coin", version: "2", chainId: 8453, verifyingContract: asset }, primaryType: "TransferWithAuthorization", types: authorizationTypes, message: parsed.payload.authorization, signature: parsed.payload.signature });
  assert.equal(recovered, buyer.address);
  const changed = { ...parsed.payload.authorization, value: "12500001" };
  assert.notEqual(await recoverTypedDataAddress({ domain: { name: "USD Coin", version: "2", chainId: 8453, verifyingContract: asset }, primaryType: "TransferWithAuthorization", types: authorizationTypes, message: changed, signature: parsed.payload.signature }), buyer.address);
  assert.equal(PaymentPayloadSchema.safeParse({ ...payload, payload: [] }).success, false);
  const oversized = PaymentRequiredSchema.safeParse({ ...required, accepts: Array(100_000).fill(null) });
  assert.equal(oversized.success, false);
  assert.equal(oversized.error.issues.length, 1);
});

test("SIWx schema remains compatible with Zod 4 and rejects malformed signatures", () => {
  const valid = { domain: "seller.example", address: buyer.address, uri: "https://seller.example/", version: "1", chainId: terms.network, type: "eip191", nonce: "nonce", issuedAt: new Date().toISOString(), resources: ["https://seller.example/order"], signature: "0x1234" };
  assert.deepEqual(SIWxPayloadSchema.parse(valid), valid);
  assert.equal(SIWxPayloadSchema.safeParse({ ...valid, signature: {} }).success, false);
});

test("CDP facilitator preserves payment requests, error outcomes and authenticated paths", async () => {
  const pair = generateKeyPairSync("ec", { namedCurve: "P-256" });
  const config = { apiKeyId: "disposable-key", apiKeySecret: pair.privateKey.export({ type: "pkcs8", format: "pem" }), baseUrl: "https://facilitator.example/custom" };
  const publicKey = await importSPKI(pair.publicKey.export({ type: "spki", format: "pem" }), "ES256");
  const client = new x402Client().register(terms.network, new ExactEvmScheme(buyer)).setSpendControls({ maxAmountPerPayment: "20" });
  const payment = await client.createPaymentPayload({ x402Version: 2, resource: { url: "https://seller.example/order" }, accepts: [terms] });
  const fetchOriginal = globalThis.fetch, requests = [];
  let rejectPayment = false, failHttp = false;
  globalThis.fetch = async (url, init) => {
    const operation = new URL(url).pathname.split("/").at(-1), headers = new Headers(init.headers);
    const auth = await jwtVerify(headers.get("authorization").slice(7), publicKey);
    assert.deepEqual(auth.payload.uris, [`${init.method} ${new URL(url).host}${new URL(url).pathname}`]);
    requests.push({ url, method: init.method, ...(init.body ? { body: JSON.parse(init.body) } : {}) });
    if (failHttp) return new Response("unavailable", { status: 503 });
    const result = operation === "supported" ? { kinds: [{ x402Version: 2, scheme: "exact", network: terms.network }], extensions: ["bazaar", "builder-code", "eip2612GasSponsoring", "erc20ApprovalGasSponsoring"], signers: { [terms.network]: [receiver] } }
      : operation === "verify" ? { isValid: !rejectPayment, ...(rejectPayment ? { invalidReason: "invalid_exact_evm_payload_signature" } : { payer: buyer.address }) }
      : { success: !rejectPayment, network: terms.network, transaction: rejectPayment ? "" : `0x${"04".repeat(32)}`, ...(rejectPayment ? { errorReason: "settlement_failed" } : { payer: buyer.address }) };
    return Response.json(result);
  };
  try {
    const factories = [createCdpFacilitatorClient, ...(baseline ? [baseline.createCdpFacilitatorClient] : [])];
    const outcomes = [];
    for (const factory of factories) {
      const facilitator = factory(config), start = requests.length;
      const supported = await facilitator.getSupported();
      const verified = await facilitator.verify(payment, terms), settled = await facilitator.settle(payment, terms);
      rejectPayment = true;
      const refused = await facilitator.verify(payment, terms), failed = await facilitator.settle(payment, terms);
      rejectPayment = false;
      assert.equal(verified.isValid, true); assert.equal(settled.success, true);
      assert.equal(refused.isValid, false); assert.equal(failed.success, false);
      failHttp = true;
      await assert.rejects(facilitator.verify(payment, terms), /503/);
      failHttp = false;
      outcomes.push({ supported, verified, settled, refused, failed, requests: requests.slice(start) });
    }
    if (baseline) assert.deepEqual(outcomes[0], outcomes[1]);
    const routes = { "POST /order": { accepts: { scheme: "exact", network: terms.network, payTo: receiver, price: "$12.50" }, resource: "https://seller.example/order", description: "eSIM", tags: ["esim"], extensions: { bazaar: { info: { input: { type: "http", method: "POST", bodyType: "json", body: { offer_id: "test" } } }, schema: {} } } } };
    const servers = [];
    for (const factory of [createX402Server, ...(baseline ? [baseline.createX402Server] : [])]) {
      const start = requests.length;
      const server = await factory({ ...config, environment: "production", payToConfig: { type: "address", evm: receiver }, routes });
      await server.initialize();
      assert.equal(requests.length - start, 1);
      assert.equal(server.payToEvmAddress, receiver);
      assert.equal((await server.resourceServer.verifyPayment(payment, terms)).isValid, true);
      assert.equal((await server.resourceServer.settlePayment(payment, terms)).success, true);
      servers.push(server);
    }
    if (baseline) assert.deepEqual(servers[0].routes, servers[1].routes);
  } finally { globalThis.fetch = fetchOriginal; }
});

test("invalid credentials and unsupported route configurations fail before payment I/O", async () => {
  await assert.rejects(generateCdpJwt({ apiKeyId: "test", apiKeySecret: "bad", requestMethod: "GET", requestHost: "example.com", requestPath: "/" }), /Invalid key format/);
  await assert.rejects(createX402Server({ payToConfig: { type: "eoa" }, routes: {} }), /existing EVM receiver/);
  await assert.rejects(createX402Server({ payToConfig: { type: "address", evm: receiver }, routes: { "GET /": { accepts: { scheme: "upto", network: terms.network } } } }), /exact EVM/);
});
