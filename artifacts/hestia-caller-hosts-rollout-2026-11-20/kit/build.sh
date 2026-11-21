#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
HEARTH=sha256:0ef2660285c29a5431cb9ed0341f33541144daaaf195c12771ff9500b4cceca0
RUNNER=sha256:2013a3fa719f81b6a890490f4b79edbd37a00d459f28de7338318348f1321d26
[ "$(docker inspect -f '{{.Image}}' hestia-hestia-1)" = "$HEARTH" ] || { echo "hearth runs another image"; exit 1; }
[ "$(docker inspect -f '{{.Image}}' hestia-hestia-runner-1)" = "$RUNNER" ] || { echo "runner runs another image"; exit 1; }
docker tag "$HEARTH" jsbase2-hestia-hearth:20261120
docker tag "$RUNNER" jsbase2-hestia-runner:20261120
docker build -q -f Dockerfile.runner -t aicom-security:hestia-runner-callerhosts-20261120 .
docker build -q -f Dockerfile.hearth -t aicom-security:hestia-hearth-callerhosts-20261120 .
