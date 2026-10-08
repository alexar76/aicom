#!/usr/bin/env bash
# Kept only so old instructions still work: the public factory mirror is published by
# scripts/publish_aicom_factory.sh, which runs the gates this copy had lost (secret scan,
# gitleaks, root classification, GitHub-only target, local-exclude purge). A second copy of
# a publish script is a second door without the first door's locks.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/scripts/publish_aicom_factory.sh" "$@"
