#!/bin/sh
# Reload nginx after a certificate is renewed.
#
# The nginx installer usually does this itself, but "usually" is not something to discover
# on the day a certificate rolls over: nginx holds the old certificate in memory until it
# is told to re-read, and a hand-written vhost (the three provider names are hand-written,
# because certbot could not install TLS into blocks that had no ssl_certificate line for it
# to replace) is exactly the case where an implicit reload is easiest to lose.
#
# Idempotent and safe: a config that fails its own test is not reloaded, so a bad edit
# elsewhere cannot take the site down through this hook.
set -e
if nginx -t >/dev/null 2>&1; then
  systemctl reload nginx
  echo "deploy hook: nginx reloaded for ${RENEWED_DOMAINS:-renewed certificate}"
else
  echo "deploy hook: nginx config does not pass -t, NOT reloading" >&2
  exit 1
fi
