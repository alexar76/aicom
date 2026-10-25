// The CDP SDK's wallet provisioning and policy schemas are unnecessary for sellers
// with existing receiver addresses. Keep the same authenticated x402 transport.
import { randomBytes } from "node:crypto";
import { SignJWT, importJWK, importPKCS8 } from "jose";
import { HTTPFacilitatorClient, x402HTTPResourceServer, x402ResourceServer } from "@x402/core/server";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { bazaarResourceServerExtension } from "@x402/extensions/bazaar";
import { BUILDER_CODE_SCHEMA, builderCodeResourceServerExtension } from "@x402/extensions/builder-code";

export const CDP_FACILITATOR_URL = "https://api.cdp.coinbase.com/platform/v2/x402";

/** CDP REST authentication; JOSE owns key import and signatures. No custom crypto. */
export async function generateCdpJwt({ apiKeyId, apiKeySecret, requestMethod, requestHost, requestPath }) {
  if (!apiKeyId || !apiKeySecret) throw new Error("CDP API key ID and secret are required");
  if (!requestMethod || !requestHost || !requestPath) throw new Error("CDP REST method, host and path are required");
  let key, alg;
  try {
    key = await importPKCS8(apiKeySecret, "ES256");
    alg = "ES256";
  } catch {
    const decoded = Buffer.from(apiKeySecret, "base64");
    if (decoded.length !== 64) throw new Error("Invalid key format - must be either PEM EC key or base64 Ed25519 key");
    key = await importJWK({ kty: "OKP", crv: "Ed25519", d: decoded.subarray(0, 32).toString("base64url"), x: decoded.subarray(32).toString("base64url") }, "EdDSA");
    alg = "EdDSA";
  }
  const now = Math.floor(Date.now() / 1000);
  return new SignJWT({ sub: apiKeyId, iss: "cdp", uris: [`${requestMethod} ${requestHost}${requestPath}`] })
    .setProtectedHeader({ alg, kid: apiKeyId, typ: "JWT", nonce: randomBytes(16).toString("hex") })
    .setIssuedAt(now).setNotBefore(now).setExpirationTime(now + 120).sign(key);
}

export function createCdpFacilitatorClient(args = {}) {
  const apiKeyId = args.apiKeyId ?? process.env.CDP_API_KEY_ID;
  const apiKeySecret = args.apiKeySecret ?? process.env.CDP_API_KEY_SECRET;
  const missing = [];
  if (!apiKeyId) missing.push("CDP_API_KEY_ID");
  if (!apiKeySecret) missing.push("CDP_API_KEY_SECRET");
  if (missing.length) throw new Error(`Missing required CDP credentials: ${missing.join(", ")}. Provide them via args or set the corresponding environment variables.`);
  const url = args.baseUrl ?? CDP_FACILITATOR_URL;
  const parsed = new URL(url), basePath = parsed.pathname.replace(/\/$/, "");
  return new HTTPFacilitatorClient({ url, createAuthHeaders: async () => {
    const entries = await Promise.all(["verify", "settle", "supported"].map(async operation => [operation, {
      Authorization: `Bearer ${await generateCdpJwt({ apiKeyId, apiKeySecret, requestMethod: operation === "supported" ? "GET" : "POST", requestHost: parsed.host, requestPath: `${basePath}/${operation}` })}`,
      "Correlation-Context": "sdkLanguage=javascript,source=aimarket-x402-cdp,sourceVersion=0.1.0",
    }]));
    return Object.fromEntries(entries);
  } });
}

// Same minimal discovery shape as the upstream CDP address-configured server.
function buildBazaarDeclaration(method, path) {
  const body = ["POST", "PUT", "PATCH"].includes(method);
  const input = { type: "http", method, ...(body ? { bodyType: "json", body: {} } : {}) };
  return {
    info: { input }, routeTemplate: path,
    schema: { properties: { input: {
      type: "object", properties: {
        type: { type: "string", const: "http" }, method: { type: "string", enum: [method] },
        ...(body ? { bodyType: { type: "string", enum: ["json"] }, body: { type: "object" } } : {}),
      }, required: ["type", "method", ...(body ? ["bodyType", "body"] : [])], additionalProperties: false,
    } } },
  };
}

/** Exact EVM routes with explicit receiver addresses, the surface used by our sellers. */
export async function createX402Server(config) {
  if (config.payToConfig?.type !== "address" || !/^0x[0-9a-fA-F]{40}$/.test(config.payToConfig.evm ?? "")) {
    throw new Error("createX402Server requires an existing EVM receiver address");
  }
  if (!config.routes || !Object.keys(config.routes).length) throw new Error("createX402Server requires at least one payment route.");
  if (config.environment !== undefined && !["production", "development"].includes(config.environment)) throw new Error("Invalid x402 environment");
  if (config.builderCode !== undefined && (typeof config.builderCode !== "string" || !/^[a-z0-9_]{1,32}$/.test(config.builderCode))) throw new Error("Invalid builder code");
  const payTo = config.payToConfig.evm;
  const routes = {};
  for (const [pattern, route] of Object.entries(config.routes)) {
    if (!route.accepts) throw new Error("An explicit x402 accepts configuration is required");
    const options = (Array.isArray(route.accepts) ? route.accepts : [route.accepts]).map(option => {
      if (option.scheme !== "exact" || !/^eip155:\d+$/.test(option.network)) throw new Error("Only configured exact EVM routes are supported");
      const receiver = option.payTo?.trim() ? option.payTo : payTo;
      if (!/^0x[0-9a-fA-F]{40}$/.test(receiver)) throw new Error("Invalid payment receiver");
      return { ...option, payTo: receiver };
    });
    const match = /^(\S+) (\/.*)$/.exec(pattern);
    routes[pattern] = { ...route, accepts: Array.isArray(route.accepts) ? options : options[0], extensions: {
      eip2612GasSponsoring: {}, erc20ApprovalGasSponsoring: {},
      ...(match && match[1] !== "*" ? { bazaar: buildBazaarDeclaration(match[1].toUpperCase(), match[2]) } : {}),
      // Preserve the existing wire declaration for already configured clients.
      "builder-code": { info: { ...(config.builderCode !== undefined ? { a: config.builderCode } : {}), s: ["cdp_sdk_server"] }, schema: BUILDER_CODE_SCHEMA },
      ...route.extensions,
    } };
  }
  const resourceServer = new x402ResourceServer(createCdpFacilitatorClient(config));
  resourceServer.register("eip155:*", new ExactEvmScheme());
  for (const extension of [
    { key: "eip2612GasSponsoring", enrichPaymentRequiredResponse: async declaration => declaration ?? {} },
    { key: "erc20ApprovalGasSponsoring", enrichPaymentRequiredResponse: async declaration => declaration ?? {} },
    bazaarResourceServerExtension, builderCodeResourceServerExtension,
  ]) resourceServer.registerExtension(extension);
  class AddressConfiguredServer extends x402HTTPResourceServer {
    #initialization;
    get resourceServer() { return resourceServer; }
    initialize() {
      this.#initialization ??= super.initialize().catch(error => { this.#initialization = undefined; throw error; });
      return this.#initialization;
    }
  }
  const server = new AddressConfiguredServer(resourceServer, routes);
  server.payToEvmAddress = payTo;
  await server.initialize();
  return server;
}
