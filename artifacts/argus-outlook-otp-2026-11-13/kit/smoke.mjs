import assert from "node:assert/strict";
import { authorizeMicrosoftMail } from "./dist/cli/commands/mail-microsoft-oauth.js";
import { canSendMail, microsoftMailScopes } from "./dist/mail/types.js";
import "./dist/cli/commands/mail.js";
import "./dist/telegram/mail.js";

const verificationUri = "https://www.microsoft.com/link";
let requests = 0;
const refresh = await authorizeMicrosoftMail({
  clientId: "afb2b823-5e84-4b15-b173-c502eb0624be",
  incomingOnly: true,
  showCode: (url, code) => {
    assert.equal(url, verificationUri);
    assert.equal(code, "FIXTURE-CODE");
  },
  signal: AbortSignal.timeout(3000),
  wait: async () => {},
  request: async (url, init) => {
    assert.equal(new URL(url).origin, "https://login.microsoftonline.com");
    if (++requests === 1) {
      assert.deepEqual(init.body.get("scope").split(" "), [
        "https://graph.microsoft.com/User.Read", "https://graph.microsoft.com/Mail.Read", "offline_access",
      ]);
      return Response.json({
        device_code: "fixture-device", user_code: "FIXTURE-CODE", verification_uri: verificationUri, expires_in: 900,
      });
    }
    assert.equal(init.body.get("device_code"), "fixture-device");
    return Response.json({ refresh_token: "fixture-refresh" });
  },
});
assert.equal(requests, 2);
assert.equal(refresh, "fixture-refresh");
assert.equal(canSendMail({ graph: true, graphIncomingOnly: true }), false);
assert.equal(canSendMail({ graph: true }), true);
assert.ok(microsoftMailScopes().includes("https://graph.microsoft.com/Mail.Send"));
console.log("Outlook incoming OAuth smoke passed with mocked Microsoft responses");
