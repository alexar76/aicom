#!/usr/bin/env bash
# Tag the two running images, then build the candidates on top of them. Refuses if a container
# no longer runs the image this kit was prepared against.
set -euo pipefail
cd "$(dirname "$0")"
HEARTH=sha256:176f205691d20629df8ed5572edbce8f45b23cfe85ac93b92d7bcf55f172f5d6
RUNNER=sha256:c238bb8a9483ab3246fc88ae9fc074571c6d03cf9af263846170dc76d388b437
[ "$(docker inspect -f '{{.Image}}' hestia-hestia-1)" = "$HEARTH" ] || { echo "hearth runs another image"; exit 1; }
[ "$(docker inspect -f '{{.Image}}' hestia-hestia-runner-1)" = "$RUNNER" ] || { echo "runner runs another image"; exit 1; }
docker tag "$HEARTH" jsbase-hestia-hearth:20261120
docker tag "$RUNNER" jsbase-hestia-runner:20261120
docker build -q -f Dockerfile.runner -t aicom-security:hestia-runner-js-20261120 .
docker build -q -f Dockerfile.hearth -t aicom-security:hestia-hearth-js-20261120 .
