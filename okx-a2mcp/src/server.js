import { createApp } from "./app.js";

const port = Number(process.env.PORT || 9480);
const host = process.env.HOST || "127.0.0.1";
const app = createApp({
  historUrl: process.env.HISTOR_URL || "https://histor.modelmarket.dev",
  publicUrl: (process.env.PUBLIC_URL || "").replace(/\/+$/, ""),
  perMinute: Number(process.env.RATE_PER_MINUTE || 30),
  ...(process.env.TRUST_PROXY ? { trustProxy: process.env.TRUST_PROXY } : {}),
});
app.listen(port, host, () => console.log(`okx-a2mcp listening on ${host}:${port}`));
