# Outlook verification code test for ARGUS

## Status on 2026-11-13

- Outlook was open in Firefox. Microsoft rejected that account for app registration because it does not have access to the Microsoft Services directory. No ARGUS application client ID, device sign-in code, or mailbox grant was available.
- The incoming-only OAuth build and 48 focused ARGUS tests passed. The Attested candidate image `aicom-security:argus-outlook-incoming-20261113` passed its offline smoke check with simulated Microsoft responses.
- The first replacement stopped at a missing checkout browser bind. After explicit owner approval, the bind was restored on the same host with mode 0600 and the existing endpoint. No credential was printed. The checkout browser did not need a restart.
- Production now runs `aicom-security:argus-outlook-incoming-20261113` (`sha256:9926296041a80f3f961f60e40b836fc74afcd2b17a41330f67b343d39d2811d3`). Docker and HTTP health passed. The new bot container authenticated to the private browser and passed the Chromium sandbox and offline page smoke. Mail status remained disconnected; no purchase or email was sent.
- The live Outlook test has not run. It requires a registered public client that supports personal Microsoft accounts, the mailbox owner's consent, and a synthetic test email.

## Run the test

Connect the Outlook.com mailbox to the running ARGUS service and enable **Verification codes** under **Permissions** in the bot's private `/mail` chat. Keep **Read** and **Send** off for this test.

Run from this directory with the address of a sender you control. If the service uses an explicit `--config` path, append that container path after the sender argument.

```sh
ssh -T attested 'docker exec -i argus node --input-type=module - sender@example.com' < check.mjs
```

Send one plain-text message with the displayed subject and body from that sender to the connected Outlook mailbox. Check that Outlook delivers the message to **Inbox**. The challenge expires in three minutes. The six digits in the prompt are generated for this test.

The check reads through ARGUS's deployed `MailService`. ARGUS uses Microsoft Graph to look for a fresh Inbox message from the selected sender with the generated reference and passes the extracted code directly to a one-use verifier in the same process. The final status is successful only if that verifier accepts the submitted code before the challenge expires. The verifier is local to the test and performs no purchase, booking or account login.

Local checks covered a successful submission, a wrong code, disabled codes-only mode, a different mail provider, permission revocation and cancellation. A separate check used ARGUS's real `MailService` and encrypted test settings with a simulated Outlook Inbox transport. The live test requires an authorized Outlook connection and the test email.
