#!/bin/sh
# Waits for `multica auth login` (run once: docker exec -it multica-daemon multica auth login), then runs the
# daemon. `multica auth status` exits 0 even when logged out, so its output is matched instead.
while multica auth status 2>&1 | grep -qi "not authenticated"; do
  sleep 30
done
exec multica daemon start --foreground
