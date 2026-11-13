# ARGUS Gmail deployment verification, 2026-11-12

ARGUS 0.3.6 runs on `attested` from image manifest
`sha256:b3497a19ab8913341c66e9af61e314280b7e0264b7c8f3cf65c7f2146b3b603a`.
The container reported healthy after rollout. Its environment and mounts were
preserved. The mail integration was disconnected at verification time.

- TypeScript compiled; 52 focused mail, keystore, Telegram and test-booking checks passed.
- The OAuth loopback flow was tested with a simulated token exchange. The final
  container was tested in isolation with a simulated Gmail API that checked the
  account and accepted exactly one MIME reply with the expected recipient,
  subject, content and thread.
- The VPS could reach Google's OAuth endpoint over HTTPS and Gmail IMAP over
  TLS. Both Gmail SMTP ports timed out. The deployed container reached the
  Gmail API and received the expected HTTP 401 from an unauthenticated request.
- Real inbox reads, code extraction and reply delivery still require mailbox
  consent and a test message. No real message was sent.

| Check | Result |
| --- | --- |
| [npm audit, lockfile](npm-audit.json) and [runtime dependencies](npm-audit-runtime.json) | No advisories reported |
| [Vulnetix public advisory and malware database](vulnetix.json), matched against the ARGUS lockfile | No matches |
| [OSV npm advisories with GHSA aliases and CISA KEV correlation](osv-ghsa-kev.json) | No matches |
| [Trivy 0.76.2, final image](trivy-https.json) | No Critical findings. 56 High records in Debian packages and 10 High records in bundled global npm dependencies. |

The final Trivy report matches the [preceding candidate](trivy.json) on
severity counts, package paths and High/Critical records. The Debian package
inventory was also unchanged from the previous production image. Application
dependency checks do not cover the entire image.
