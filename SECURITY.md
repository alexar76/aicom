# Security Policy

## Supported versions

Security fixes are applied to the latest `main` branch.

## Reporting vulnerabilities

Do not open public issues for vulnerabilities.

Report privately to project maintainers with:

- affected component and commit/version
- reproduction steps or proof of concept
- impact assessment
- suggested remediation (optional)

If you already opened a public issue by mistake, edit it immediately to remove sensitive details.

## Scope

- Authentication and authorization flows
- Payment and wallet integration paths
- Sandbox/code execution boundaries
- Secret storage and key management
- CI/CD credential handling

## Secret handling policy

- Never commit API tokens, private keys, wallet addresses intended for production, internal host IPs, or user credentials.
- Use environment variables, secret managers, or runtime-local config files excluded from VCS.
- Rotate compromised credentials immediately and invalidate old tokens.

## Response SLA

- Initial triage: within 72 hours
- Severity classification and remediation plan: within 7 days
- Status updates: at least weekly until resolved
