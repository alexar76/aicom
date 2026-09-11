#!/usr/bin/env bash
# Unique Docker image tag for deploy/CI (avoids BuildKit "image already exists" on rebuild).
# Usage: export AICOM_IMAGE_TAG="$(./scripts/docker_image_tag.sh)"
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SHA="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo nogit)"
DATE="$(date -u +%Y%m%d)"
echo "prod-${DATE}-${SHA}"
