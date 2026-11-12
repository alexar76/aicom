#!/bin/sh
# Run only in an approved remote verification host.
set -eu
host_label=$1
case "$host_label" in attested|blip) ;; *) exit 64 ;; esac
base=/opt/aicom-verify/20261108-all-tree
original=$base/blog-static
own=$base/blog-static-refresh
image=sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5
mkdir -p "$own/results" "$own/scripts"
cp "$own/receipts/verify_refresh.py" "$own/scripts/verify_refresh.py"
chown -R 1000:1000 "$own"
chmod 700 "$own"
printf '%s\n' 'ec5cf519409f454c03eb890720ccbe584781f503082255d012e95678834b17ed  verify_static.py' | (cd "$original/scripts" && sha256sum -c -) > "$own/results/original-proof-check.txt"
sha256sum "$own/scripts/verify_refresh.py" "$original/scripts/verify_static.py" > "$own/results/proof-source.sha256"
container=aicom-blog-static-refresh-check-$host_label
docker create --name "$container" --runtime runsc --network none --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --cpus 1 --memory 1g --tmpfs /tmp:rw,nosuid,nodev,size=128m,mode=1777 --tmpfs /work:rw,nosuid,nodev,size=512m,mode=1777 --mount type=bind,src="$own/input",dst=/input,readonly --mount type=bind,src="$own/receipts",dst=/receipts,readonly --mount type=bind,src="$original/deps",dst=/deps,readonly --mount type=bind,src="$base/deps/python-gates",dst=/gate-deps,readonly --mount type=bind,src="$original/cache",dst=/cache,readonly --mount type=bind,src="$original/scripts",dst=/original-scripts,readonly --mount type=bind,src="$own/scripts",dst=/scripts,readonly --mount type=bind,src="$own/results",dst=/results --workdir /work -e HOME=/work -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/deps:/gate-deps -e "HOST_LABEL=$host_label" "$image" python /scripts/verify_refresh.py > "$own/results/container-id.txt"
docker inspect --format '{"runtime":{{json .HostConfig.Runtime}},"network":{{json .HostConfig.NetworkMode}},"user":{{json .Config.User}},"readonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"capDrop":{{json .HostConfig.CapDrop}},"securityOpt":{{json .HostConfig.SecurityOpt}},"tmpfs":{{json .HostConfig.Tmpfs}},"workingDir":{{json .Config.WorkingDir}},"mounts":{{json .Mounts}},"image":{{json .Image}}}' "$container" > "$own/results/build-isolation.json"
docker start -a "$container" > "$own/results/run.log" 2>&1 || true
test_exit=$(docker inspect --format '{{.State.ExitCode}}' "$container")
printf '%s\n' "$test_exit" > "$own/results/exit-code.txt"
cat "$own/results/run.log"
docker rm "$container" > "$own/results/removed-containers.txt"
docker ps -a --filter "name=^/aicom-blog-static-refresh-check-$host_label$" --format '{{.Names}}' > "$own/results/remaining-containers.txt"
test ! -s "$own/results/remaining-containers.txt"
test "$test_exit" = 0
printf '%s\n' 'PASS: refreshed full static build; runsc network=none UID=1000; source/deps/cache readonly; tmpfs work and container removed' > "$own/results/completion.txt"
