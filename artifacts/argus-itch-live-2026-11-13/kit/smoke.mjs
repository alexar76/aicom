import assert from "node:assert/strict";
import { configuredItchPurchase } from "./dist/checkout/itch-purchase.js";
import { ITCH_PRODUCT, isCheckoutBrowserEndpoint } from "./dist/checkout/itch-browser.js";
import { createProviderActivityReporter } from "./dist/monitor/provider-events.js";
import { TelegramBot } from "./dist/telegram/bot.js";
import { cmdMail } from "./dist/cli/commands/mail.js";
import { Runtime } from "./dist/runtime.js";

assert.equal(typeof TelegramBot, "function");
assert.equal(typeof Runtime, "function");
assert.equal(typeof cmdMail, "function");
assert.equal(ITCH_PRODUCT.maxCents, 500);
assert.equal(configuredItchPurchase("/tmp", "uni"), undefined);
assert.equal(configuredItchPurchase("/tmp", "live"), undefined);
assert.equal(typeof createProviderActivityReporter({ url: "", token: "" }, { debug() {} }), "function");
assert(isCheckoutBrowserEndpoint("ws://argus-checkout-browser:47871/" + "a".repeat(64)));
assert(!isCheckoutBrowserEndpoint("wss://elsewhere.example/" + "a".repeat(64)));
console.log("Checkout/Telegram/mail/provider imports and disabled-mode boundaries pass");
