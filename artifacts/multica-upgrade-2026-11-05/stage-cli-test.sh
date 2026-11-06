#!/bin/sh
# Runs inside a throwaway container on the isolated stand network. Nothing secret is printed.
set -u
export MULTICA_SERVER_URL=http://mstage-backend:8080
export MULTICA_TOKEN="$(jq -r '.token // .access_token // empty' /cfg.json)"
ws="$(jq -r '.workspace_id // .current_workspace_id // .workspace // empty' /cfg.json)"
[ -n "$ws" ] && export MULTICA_WORKSPACE_ID="$ws"
[ -n "$MULTICA_TOKEN" ] && echo "token loaded (${#MULTICA_TOKEN} chars)" || echo "NO TOKEN in config"
M=/cli/multica
$M version | head -1
echo "-- issue get MY-66:"; $M issue get MY-66 --output json | jq -c '{identifier, assignee_type, assignee_id, status}'
echo "-- wrapper get own task:"; PATH=/cli:$PATH /w/order-task get MY-66 | jq -c '{identifier, status}'; echo "exit=$?"
echo "-- wrapper get other agent's task:"; PATH=/cli:$PATH /w/order-task get MY-60 >/dev/null; echo "exit=$?"
echo "-- move MY-66 to in_review, then wrapper done:"; $M issue status MY-66 in_review --no-start >/dev/null && echo "in_review set"
PATH=/cli:$PATH /w/order-task done MY-66; echo "exit=$?"
$M issue get MY-66 --output json | jq -c '{identifier, status}'
echo "-- CLI commands the kit uses:"; for c in "agent env set" "agent update" "autopilot trigger-add" "skill import" "issue status"; do $M $c --help >/dev/null 2>&1 && echo "ok: $c" || echo "MISSING: $c"; done
$M autopilot list --output json 2>/dev/null | jq -r '.[]? | "\(.title) | \(.status)"' | head -6
