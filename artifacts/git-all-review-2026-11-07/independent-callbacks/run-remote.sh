#!/bin/sh
# Execute only on the approved remote sandbox; no production mounts or services.
set -eu
host_label=$1
case "$host_label" in attested|blip) ;; *) exit 64 ;; esac
base=/opt/aicom-verify/20261108-all-tree
source_root=$base/source-v4
own_root=$base/independent-callbacks
execution_source=$own_root/source
image=sha256:76baad6037690d6e8c4397fbcaef17bca6f19eecef822b708fe8fa3417d30bb5
mkdir -p "$own_root/results" "$own_root/deps/kova" "$own_root/deps/aegis" "$execution_source"
chown -R 1000:1000 "$own_root"
chmod 700 "$own_root"
printf '%s\n' '1400f9f8e6f0b104298835b1f9bcfd35f4a75aa3' > "$own_root/results/source-tree.txt"
printf '%s\n' '7085e9f236ccd276b89a3f864421751fb468f9da18b17b05376ffccb40068f16' > "$own_root/results/source-shamap.txt"
cd "$own_root/config"
sha256sum -c config.sha256 > "$own_root/results/config-source-check.txt"
cp config.sha256 "$own_root/results/config-source.sha256"
cd "$source_root"
sha256sum independent/kova-gateway/backend/tests/test_callback_http.py independent/verified-execution-hub/backend/tests/test_callback_http.py > "$own_root/results/callback-source.sha256"
printf '%s\n' 'b2b43e8fd23060aec96ec7597f7307bb14a329eedb7c1a9f86317c26a4e94560  independent/kova-gateway/backend/tests/test_callback_http.py' '6c97774bc4da6bae667704bc85faf5af468ac366bda2bd21068f17bab2f8b858  independent/verified-execution-hub/backend/tests/test_callback_http.py' | sha256sum -c - > "$own_root/results/callback-source-check.txt"
find independent/kova-gateway/backend independent/verified-execution-hub/backend -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum > "$own_root/results/python-source-before.sha256"
prepare=aicom-callbacks-$host_label-source-prepare
docker create --name "$prepare" --runtime runsc --network none --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 64 --cpus 1 --memory 256m --tmpfs /tmp:rw,noexec,nosuid,size=32m,uid=1000,gid=1000,mode=1777 --mount type=bind,src="$source_root",dst=/snapshot,readonly --mount type=bind,src="$own_root/config",dst=/config,readonly --mount type=bind,src="$execution_source",dst=/prepared "$image" sh -ec 'mkdir -p /prepared/independent; cp -a /snapshot/independent/kova-gateway /snapshot/independent/verified-execution-hub /prepared/independent/; cp /config/kova/pyproject.toml /prepared/independent/kova-gateway/pyproject.toml; cp /config/aegis/pyproject.toml /prepared/independent/verified-execution-hub/pyproject.toml' > "$own_root/results/source-prepare-container.txt"
docker inspect --format '{"runtime":{{json .HostConfig.Runtime}},"network":{{json .HostConfig.NetworkMode}},"user":{{json .Config.User}},"readonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"mounts":{{json .Mounts}},"image":{{json .Image}}}' "$prepare" > "$own_root/results/source-prepare-isolation.json"
docker start -a "$prepare" > "$own_root/results/source-prepare.log" 2>&1 || true
prepare_exit=$(docker inspect --format '{{.State.ExitCode}}' "$prepare")
printf '%s\n' "$prepare_exit" > "$own_root/results/source-prepare-exit.txt"
test "$prepare_exit" = 0
cd "$execution_source"
sha256sum -c "$own_root/results/python-source-before.sha256" > "$own_root/results/prepared-python-source-check.txt"
cmp independent/kova-gateway/pyproject.toml "$own_root/config/kova/pyproject.toml"
cmp independent/verified-execution-hub/pyproject.toml "$own_root/config/aegis/pyproject.toml"
for project in kova aegis; do
  case "$project" in
    kova) project_path=independent/kova-gateway ;;
    aegis) project_path=independent/verified-execution-hub ;;
  esac
  setup=aicom-callbacks-$host_label-deps-$project
  if ! test -f "$own_root/results/$project-setup-exit.txt"; then
  docker create --name "$setup" --runtime runsc --network bridge --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --cpus 1 --memory 1g --tmpfs /tmp:rw,noexec,nosuid,size=256m,uid=1000,gid=1000,mode=1777 --mount type=bind,src="$source_root/$project_path/backend",dst=/requirements,readonly --mount type=bind,src="$own_root/deps/$project",dst=/deps --mount type=bind,src="$own_root/results",dst=/results -e HOME=/tmp -e PYTHONDONTWRITEBYTECODE=1 "$image" python -m pip install --index-url https://pypi.org/simple --disable-pip-version-check --no-cache-dir --only-binary=:all: --report "/results/$project-dependencies.json" --target /deps -r /requirements/requirements-dev.txt > "$own_root/results/$project-setup-container.txt"
  docker inspect --format '{"runtime":{{json .HostConfig.Runtime}},"network":{{json .HostConfig.NetworkMode}},"user":{{json .Config.User}},"readonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"mounts":{{json .Mounts}},"image":{{json .Image}}}' "$setup" > "$own_root/results/$project-setup-isolation.json"
  docker start -a "$setup" > "$own_root/results/$project-setup.log" 2>&1 || true
  setup_exit=$(docker inspect --format '{{.State.ExitCode}}' "$setup")
  printf '%s\n' "$setup_exit" > "$own_root/results/$project-setup-exit.txt"
  else
    setup_exit=$(cat "$own_root/results/$project-setup-exit.txt")
  fi
  test "$setup_exit" = 0
  container=aicom-callbacks-$host_label-test-$project
  docker create --name "$container" --runtime runsc --network none --user 1000:1000 --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --cpus 1 --memory 1g --tmpfs /tmp:rw,noexec,nosuid,size=256m,uid=1000,gid=1000,mode=1777 --tmpfs /work:rw,nosuid,size=256m,uid=1000,gid=1000,mode=1777 --mount type=bind,src="$execution_source",dst=/source,readonly --mount type=bind,src="$own_root/deps/$project",dst=/deps,readonly --mount type=bind,src="$own_root/results",dst=/results --workdir /work -e HOME=/work -e PYTHONDONTWRITEBYTECODE=1 -e PYTHONPATH=/deps -e KOVA_DATA_DIR=/work/kova-data -e AEGIS_DATA_DIR=/work/aegis-data "$image" python -m pytest -c "/source/$project_path/pyproject.toml" "/source/$project_path/backend/tests/test_callback_http.py" -p no:cacheprovider --basetemp "/work/$project-pytest" --junitxml "/results/$project-junit.xml" > "$own_root/results/$project-test-container.txt"
  docker inspect --format '{"runtime":{{json .HostConfig.Runtime}},"network":{{json .HostConfig.NetworkMode}},"user":{{json .Config.User}},"readonlyRootfs":{{json .HostConfig.ReadonlyRootfs}},"capDrop":{{json .HostConfig.CapDrop}},"securityOpt":{{json .HostConfig.SecurityOpt}},"tmpfs":{{json .HostConfig.Tmpfs}},"workingDir":{{json .Config.WorkingDir}},"mounts":{{json .Mounts}},"image":{{json .Image}}}' "$container" > "$own_root/results/$project-test-isolation.json"
  docker start -a "$container" > "$own_root/results/$project-test.log" 2>&1 || true
  test_exit=$(docker inspect --format '{{.State.ExitCode}}' "$container")
  printf '%s\n' "$test_exit" > "$own_root/results/$project-test-exit.txt"
  cat "$own_root/results/$project-test.log"
  test "$test_exit" = 0
done
cd "$execution_source"
find independent/kova-gateway/backend independent/verified-execution-hub/backend -type f -name '*.py' -print0 | sort -z | xargs -0 sha256sum > "$own_root/results/python-source-after.sha256"
cmp "$own_root/results/python-source-before.sha256" "$own_root/results/python-source-after.sha256"
cmp independent/kova-gateway/pyproject.toml "$own_root/config/kova/pyproject.toml"
cmp independent/verified-execution-hub/pyproject.toml "$own_root/config/aegis/pyproject.toml"
docker rm "$prepare" >> "$own_root/results/removed-containers.txt"
for project in kova aegis; do
  find "$own_root/deps/$project" -type f -print0 | sort -z | xargs -0 sha256sum > "$own_root/results/$project-dependencies.sha256"
  docker rm "aicom-callbacks-$host_label-deps-$project" "aicom-callbacks-$host_label-test-$project" >> "$own_root/results/removed-containers.txt"
done
docker ps -a --filter "name=^/aicom-callbacks-$host_label-" --format '{{.Names}}' > "$own_root/results/remaining-containers.txt"
test ! -s "$own_root/results/remaining-containers.txt"
printf '%s\n' 'PASS: 2 separate callback suites; runsc network=none UID=1000; source+dependencies readonly; temporary state removed with containers' > "$own_root/results/completion.txt"
