# User Cases

## Case 1: Solo developer scanning a side project

**Persona**: Alex, freelance web developer. Maintains an open-source npm package and a few private client projects on their laptop.

**Situation**: Alex reads about a supply-chain attack on a popular npm dependency. They want to check their own projects quickly without uploading code to a third-party service or paying for a SaaS subscription.

**Flow**:

1. Alex opens Local Security Audit and points it at their local project folder.
2. The app detects a `package.json` and `package-lock.json`, parses the dependency tree, and notes the app has no cached CVE rules.
3. Alex clicks "Buy fresh CVE feed" from the marketplace. The app discovers available CVE capabilities for the npm ecosystem, opens a $5 USDT payment channel, purchases the latest feed, and verifies the TEE attestation.
4. The scan runs locally: 78 dependencies checked, 3 CVEs found (one critical, two moderate).
5. Alex reviews the results, clicks each CVE to see the remediation advice, and fixes the issues.
6. A previously-unnoticed hardcoded AWS access key is flagged by the secret scanner. Alex rotates the key immediately.
7. Alex opts to contribute an anti-pattern signature for the hardcoded key pattern to the marketplace — the actual key is never transmitted, only a structural hash.

**Outcome**: Alex catches a critical CVE and a leaked credential before publishing the next release. Total cost: $5 for the CVE feed. No code uploaded.

---

## Case 2: Startup CTO auditing pre-launch

**Persona**: Priya, CTO of a 12-person fintech startup. They are weeks away from launching a mobile payment app. The team has been moving fast; security debt is unknown.

**Situation**: Priya needs a comprehensive security audit before the launch but cannot upload their proprietary payment code to any SaaS platform. Budget is tight — a full pentest quote came back at $40k.

**Flow**:

1. Priya installs Local Security Audit on her secure laptop and clones all company repos: `payment-api`, `mobile-sdk`, `admin-dashboard`, `infrastructure`.
2. She runs the scanner on `payment-api` first. The app discovers 14 different dependency manifests across the monorepo.
3. From the marketplace, she purchases:
   - **CVE feed** for Rust and Node.js ecosystems ($5)
   - **Exploit DB patterns** for financial API misconfigurations ($8)
   - **Secret-scanning rules** fine-tuned for payment gateway keys ($3)
4. Each purchase is TEE-verified. Priya inspects the attestation receipts to confirm the feeds come from a verified enclave.
5. The scan across all repos runs overnight (background mode). Results:
   - 12 CVEs across dependencies (2 critical)
   - 4 exposed API keys in test files
   - 1 hardcoded database credential in a config file that was accidentally committed
   - 2 instances of insecure cryptographic algorithm usage
6. Priya exports a SARIF report and shares it with the team. Each finding links to remediation docs.
7. The team fixes all findings before launch week. Priya keeps the CVE feed subscription active for weekly re-scans.

**Outcome**: Launch proceeds on schedule. Total cost: $16 in marketplace feeds vs. $40k for a pentest. Code never left Priya's laptop.

---

## Case 3: Agency checking client code before handoff

**Persona**: Marcus, lead engineer at a digital agency that builds Shopify stores and custom web apps for clients.

**Situation**: Marcus's team is about to hand off a completed e-commerce platform to a client. A previous handoff went badly when the client's security team found hardcoded credentials in the codebase. Marcus needs to prevent a repeat.

**Flow**:

1. Marcus's team maintains a shared set of custom secret-scanning rules they've built up over dozens of projects. These are stored as signature hashes in the marketplace.
2. Before handoff, Marcus runs Local Security Audit on the client's repository.
3. The app syncs the team's custom rule signatures from the marketplace — signature hashes only, no source code.
4. The scan runs and produces a clean report: no secrets, no CVEs in production dependencies, no insecure patterns.
5. Marcus exports a signed JSON report to include in the handoff package. The report is timestamped and includes TEE receipts for all purchased feeds.
6. The client's security team can inspect the report and independently verify that:
   - The CVE data came from a TEE-verified marketplace source
   - The scan was performed locally (no code upload)
   - The results are cryptographically signed

**Outcome**: Clean handoff with verifiable security report. The client's security team approves. Marcus's agency builds trust and differentiates itself from competitors who skip security checks.

---

## Summary

| Scenario | User | Key Need | Marketplace Cost |
|----------|------|----------|-----------------|
| Solo dev scanning side project | Freelancer | Quick, cheap, private | $5–$10 |
| Startup CTO pre-launch audit | Startup | Comprehensive, no code upload | $16–$30 |
| Agency client handoff | Agency | Verifiable report, trust | $5–$15 + custom sigs |
