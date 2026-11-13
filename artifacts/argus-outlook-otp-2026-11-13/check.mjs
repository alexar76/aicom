import { randomInt, randomUUID } from "node:crypto";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { setTimeout as delay } from "node:timers/promises";

const testDuration = 3 * 60_000;

export async function checkOutlookOtp(mail, sender, show, signal = AbortSignal.timeout(testDuration)) {
  const settings = mail.settings();
  function codesOnly(account) {
    return account?.accountId === settings?.accountId && account?.auth === "microsoft-oauth" && account.graph === true
      && account.permissions.otp && !account.permissions.read && !account.permissions.send;
  }
  if (!codesOnly(settings)) {
    show("FAIL: connect an Outlook.com mailbox and enable only verification codes.");
    return 1;
  }

  const reference = randomUUID().replaceAll("-", "");
  const subject = `ARGUS verification check ${reference}`;
  const expectedCode = String(randomInt(100_000, 1_000_000));
  const notBefore = Date.now();
  let submitted = false;

  function submit(challengeReference, code) {
    if (submitted || signal.aborted || Date.now() >= notBefore + testDuration) return false;
    submitted = true;
    return challengeReference === reference && code === expectedCode;
  }

  show([
    "Send one plain-text email from the selected sender to the connected Outlook Inbox within three minutes.",
    `Subject: ${subject}`,
    `Body: Verification code: ${expectedCode}. Request ${reference}`,
    "The code above belongs to this synthetic test.",
  ].join("\n"));

  try {
    while (!signal.aborted && codesOnly(mail.settings())) {
      const code = await mail.readCode({
        accountId: settings.accountId, sender, subjectIncludes: subject, reference, notBefore, signal,
      });
      if (code !== null) {
        if (codesOnly(mail.settings()) && submit(reference, code)) {
          show("PASS: Outlook code received and accepted by the local test verifier.");
          return 0;
        }
        break;
      }
      await delay(6000, undefined, { signal });
    }
  } catch {
    // Provider errors and retrieved values stay out of the report.
  }
  show("FAIL: no code was accepted. Check Inbox delivery, sender and ARGUS permissions.");
  return 1;
}

async function main() {
  const [senderArg, configPath, ...extra] = process.argv.slice(2);
  if (!senderArg || extra.length > 0) {
    console.error("Usage from the ARGUS working directory: node --input-type=module - <sender> [config-path]");
    return 1;
  }
  try {
    const { loadConfig } = await import(pathToFileURL(resolve("dist/config.js")).href);
    const { MailService, mailAddress } = await import(pathToFileURL(resolve("dist/mail/index.js")).href);
    const sender = mailAddress(senderArg);
    const { config } = loadConfig(configPath);
    return await checkOutlookOtp(new MailService(config.stateDir), sender, console.log);
  } catch {
    console.error("FAIL: could not start the check. Verify the sender address, ARGUS configuration and mailbox setup.");
    return 1;
  }
}

if (import.meta.main) {
  process.exitCode = await main();
}
