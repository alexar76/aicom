# Contributing

Thanks for helping improve AI-Factory.

## Development workflow

1. Fork the repo and create a feature branch from `main`.
2. Keep PRs focused (one behavioral change per PR whenever possible).
3. Run checks locally before opening a PR.
4. Update docs/tests together with code changes.

## Local checks

- Python syntax (touched files):
  - `python3 -m py_compile <file1.py> <file2.py>`
- Backend tests:
  - `.venv/bin/python -m pytest -q`
- Frontend build:
  - `cd web/frontend && npm run build`

## Pull request requirements

- Explain **why** the change is needed.
- Include a test plan with commands and observed results.
- Mention config/env changes explicitly.
- Keep secrets out of commits (tokens, keys, internal hosts, wallet addresses).
- Note backward compatibility impact for APIs and pipeline behavior.

## Commit message style

- Imperative mood and concise subject.
- Example: `Fix storefront eligibility fallback for build-time data access`

## Reporting bugs and proposing features

- Use issues with:
  - expected behavior
  - current behavior
  - repro steps
  - logs/screenshots where relevant

## Good first contributions

- Improve docs clarity and examples.
- Add focused tests around quality gates and state transitions.
- UI/UX polish in admin filtering and observability panels.
