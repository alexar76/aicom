#!/bin/sh
# Run OKX's A2A daemon in the foreground once the installer has put it on PATH; until then, wait.
while ! command -v okx-a2a >/dev/null 2>&1; do sleep 15; done
exec okx-a2a run
