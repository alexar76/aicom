# ARGUS itch.io and Gmail checks

Attested ARGUS runs the owner-only checkout with an address in a private receipt file, a temporary Laso session and a sandboxed browser sidecar. The deployment verified the Compose delta, kept the existing bot volume and pin, and passed container and HTTP health checks. [ARGUS rollout](argus-checkout-switch.log) · [Browser isolation](../../argus/deploy/checkout-browser/README.md)

The product page loaded through the live sidecar and showed the $2.99 base price. The page seen from Attested omits the billing address panel. After installing the direct-form branch, the merchant's first purchase request redirected to a checkout session. The next GET redirected to the itch.io homepage before Stripe opened, including when the checkout GET used the browser context cookies and the public purchase page as Referer. No card authorization or payment POST occurred. Laso returned $5 available and no itch.io debit. [Checkout trace](live-preflight-referer.ndjson)

The subsequent rollout added the owner-only `/recover_itch` command for delivering an existing purchase from its private receipt. The overlay reached healthy status. Twenty-five focused tests passed, including ten Chromium tests with simulated checkout. No paid receipt was available to test live delivery. [Recovery rollout](argus-checkout-recovery.log)

The running ARGUS accepts a Gmail app password through its hidden setup prompt or a Google Desktop app OAuth JSON. Both can run in incoming-only mode. Gmail IMAP at 993 and Google OAuth over 443 passed TLS from Attested. SMTP at 465 and 587 timed out. The receipt address is configured, while mailbox authorization awaits owner interaction. Local tests covered matching an isolated synthetic code and submitting it to a test booking provider. [Mail setup](../../argus/docs/mail.md)

The ARGUS provider event sender uses the public Monitor origin for this stream. A live, free Laso merchant lookup increased the published success count. [Laso event check](laso-telemetry-check.json) · [Monitor deployment](../alien-monitor-provider-events-2026-11-13/README.md) · [METIS canary](../metis-provider-events-2026-11-13/README.md)
