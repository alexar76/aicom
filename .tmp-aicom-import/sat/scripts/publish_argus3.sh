#!/usr/bin/env bash
# Deprecated wrapper — npm rejects bare `argus3`; use publish_argus_3.sh (argus-3).
exec "$(dirname "$0")/publish_argus_3.sh" "$@"
