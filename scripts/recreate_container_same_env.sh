#!/usr/bin/env bash
# Recreate a container on a new image while preserving the environment it was started with.
#
#   ./recreate_container_same_env.sh <container> <new-image>
#
# Why this exists: several production containers on this fleet were started with `docker run`
# and carry environment the compose files never mention — on alien-monitor that is 23 variables
# including DEEPSEEK_API_KEY, OPENROUTER_API_KEY and ALIEN_API_TOKEN. Letting `docker compose up`
# adopt those names would silently start them without the keys, which is exactly the "quietly
# degraded instead of loudly broken" outcome the no-mocks rule is about.
#
# The old container is renamed rather than removed, so a rollback is `docker rm -f NAME &&
# docker rename NAME-pre-<ts> NAME && docker start NAME`.
set -euo pipefail

name="${1:?container name required}"
image="${2:?new image required}"
stamp="$(date +%s)"
envfile="/tmp/${name}.env.${stamp}"

command -v python3 >/dev/null || { echo "python3 required" >&2; exit 2; }
docker inspect "$name" >/dev/null || exit 1

# Dump the environment through Python rather than a shell loop: values contain '=' and spaces,
# and a value containing a newline cannot survive --env-file at all, so detect that and stop
# instead of writing a file docker would misparse into two half-variables.
docker inspect "$name" --format '{{json .Config.Env}}' | python3 -c '
import json, sys
env = json.load(sys.stdin)
bad = [e.split("=", 1)[0] for e in env if "\n" in e or "\r" in e]
if bad:
    sys.exit("refusing: newline in value of " + ", ".join(bad))
with open(sys.argv[1], "w") as fh:
    for entry in env:
        fh.write(entry + "\n")
print("captured %d variables" % len(env))
' "$envfile"
chmod 600 "$envfile"

mapfile -t mount_args < <(
  docker inspect "$name" --format '{{range .Mounts}}{{.Source}}:{{.Destination}}:{{if .RW}}rw{{else}}ro{{end}}{{println}}{{end}}' \
    | sed '/^$/d' | sed 's/^/-v/'
)
# Published ports, as -p flags. Host-network containers have none — they bind directly — but a
# bridge container that loses its mapping is unreachable while looking perfectly healthy, which
# is the same silent failure this script exists to prevent.
mapfile -t port_args < <(
  docker inspect "$name" --format '{{json .HostConfig.PortBindings}}' | python3 -c '
import json, sys
for container_port, binds in (json.load(sys.stdin) or {}).items():
    for b in binds or []:
        host_ip, host_port = b.get("HostIp", ""), b.get("HostPort", "")
        prefix = f"{host_ip}:" if host_ip else ""
        print(f"{prefix}{host_port}:{container_port}")
'
)

netmode="$(docker inspect "$name" --format '{{.HostConfig.NetworkMode}}')"
restart="$(docker inspect "$name" --format '{{.HostConfig.RestartPolicy.Name}}')"
user="$(docker inspect "$name" --format '{{.Config.User}}')"
mapfile -t cmd_args < <(docker inspect "$name" --format '{{range .Config.Cmd}}{{println .}}{{end}}' | sed '/^$/d')

final=(-d --name "$name" --network "$netmode")
[[ -n "$restart" && "$restart" != "no" ]] && final+=(--restart "$restart")
[[ -n "$user" ]] && final+=(--user "$user")
final+=(--env-file "$envfile")
for m in "${mount_args[@]}"; do final+=(-v "${m#-v}"); done
for p in "${port_args[@]}"; do [[ -n "$p" ]] && final+=(-p "$p"); done
# EXTRA_PORTS exists for the case where the container we are copying has already lost a mapping
# it is supposed to have: modelmarket-hub also publishes 9460 -> 8080 for the THEMIS sidecar that
# shares its netns, and a hub deploy that forgets it leaves THEMIS reachable by nothing while
# still reporting healthy. Space-separated, same syntax as -p.
for p in ${EXTRA_PORTS:-}; do final+=(-p "$p"); done

echo "== renaming the old container (rollback path) =="
docker stop "$name" >/dev/null
docker rename "$name" "${name}-pre-${stamp}"

echo "== starting $name on $image =="
docker run "${final[@]}" "$image" "${cmd_args[@]}" >/dev/null

echo "== environment check: old vs new =="
docker inspect "${name}-pre-${stamp}" --format '{{range .Config.Env}}{{println .}}{{end}}' | sort > "/tmp/${name}.old.$stamp"
docker inspect "$name" --format '{{range .Config.Env}}{{println .}}{{end}}' | sort > "/tmp/${name}.new.$stamp"
if diff -q "/tmp/${name}.old.$stamp" "/tmp/${name}.new.$stamp" >/dev/null; then
  echo "  identical ($(wc -l < "/tmp/${name}.new.$stamp" | tr -d ' ') variables)"
else
  echo "  DIFFERS:"; diff "/tmp/${name}.old.$stamp" "/tmp/${name}.new.$stamp" | head -20
fi

old_ports="$(docker inspect "${name}-pre-${stamp}" --format '{{json .HostConfig.PortBindings}}')"
new_ports="$(docker inspect "$name" --format '{{json .HostConfig.PortBindings}}')"
if [[ "$old_ports" == "$new_ports" ]]; then
  echo "== ports preserved: $new_ports"
else
  echo "== PORTS DIFFER: was $old_ports now $new_ports" >&2
fi
rm -f "$envfile"
echo "rollback: docker rm -f $name && docker rename ${name}-pre-${stamp} $name && docker start $name"
