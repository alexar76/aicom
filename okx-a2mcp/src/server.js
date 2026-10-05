import { readFileSync } from "node:fs";
import { createApp } from "./app.js";
import { resilientPaywall } from "./x402.js";

const port = Number(process.env.PORT || 9480);
const host = process.env.HOST || "127.0.0.1";
const publicUrl = (process.env.PUBLIC_URL || "").replace(/\/+$/, "");

// x402 is on only when both a CDP key file and a receiving address are configured. Building it
// needs the facilitator; a failure there is retried in the background and never stops the free routes.
const paywall = resilientPaywall({
  keyFile: process.env.CDP_KEY_FILE,
  payTo: process.env.X402_PAY_TO,
  price: process.env.X402_PRICE || "$0.001",
  publicUrl,
  // The hub capability twins are listed only when the gateway has a hub account to buy with.
  serviceIds: ["histor-check", "warden-scan",
    ...(process.env.HUB_API_KEY_FILE ? ["weather-now", "air-quality-now", "nearby-sensors", "fair-random"] : []),
    // Two HESTIA agents, when the gateway holds a seller key on the hearth (src/hearth.js).
    ...(process.env.HEARTH_API_KEY_FILE ? ["x402-check", "mcp-diff"] : [])],
});

const app = createApp({
  historUrl: process.env.HISTOR_URL || "https://histor.modelmarket.dev",
  publicUrl,
  perMinute: Number(process.env.RATE_PER_MINUTE || 30),
  ...(process.env.TRUST_PROXY ? { trustProxy: process.env.TRUST_PROXY } : {}),
  // The buyer-id key from a mounted file (CALLER_ID_SECRET_FILE), so it stays out of `docker inspect`.
  ...(process.env.CALLER_ID_SECRET_FILE ? { callerSecret: readFileSync(process.env.CALLER_ID_SECRET_FILE, "utf8").trim() }
    : process.env.CALLER_ID_SECRET ? { callerSecret: process.env.CALLER_ID_SECRET } : {}),
  ...(process.env.FREE_HISTOR_PER_MINUTE ? { freeHistorPerMinute: Number(process.env.FREE_HISTOR_PER_MINUTE) } : {}),
  // The gateway's hub credit-account key, from a mounted file like the other secrets.
  ...(process.env.HUB_API_KEY_FILE ? { hubApiKey: readFileSync(process.env.HUB_API_KEY_FILE, "utf8").trim() } : {}),
  ...(process.env.HUB_URL ? { hubUrl: process.env.HUB_URL } : {}),
  // The gateway's seller key on the hearth, from a mounted file like the other secrets.
  ...(process.env.HEARTH_API_KEY_FILE ? { hearthApiKey: readFileSync(process.env.HEARTH_API_KEY_FILE, "utf8").trim() } : {}),
  ...(process.env.HEARTH_URL ? { hearthUrl: process.env.HEARTH_URL } : {}),
  paywall,
});
app.listen(port, host, () =>
  console.log(`okx-a2mcp listening on ${host}:${port}` +
    (paywall ? `; x402 ${paywall.price} on ${paywall.network} to ${paywall.payTo}: ${paywall.paths.join(", ")}${paywall.state.ready ? "" : " (starting)"}` : "; x402 off")),
);
