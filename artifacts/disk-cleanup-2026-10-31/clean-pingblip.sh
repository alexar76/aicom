set -u
echo "before: $(df -h / | tail -1)"
echo "running builds: $(pgrep -fa 'docker build|buildx|buildkit' | grep -v pgrep | wc -l)"
for img in pingblip-pingblip:rekt-before-20261027 pingblip-forge:rekt-before-20261027 pingblip-world:rekt-before-20261027; do
  id=$(docker image inspect --format '{{.Id}}' "$img" 2>/dev/null) || { echo "absent $img"; continue; }
  if docker ps -a --format '{{.ID}}' | xargs -r docker inspect --format '{{.Image}}' | grep -q "$id"; then echo "kept $img (a container uses it)"; continue; fi
  docker rmi "$img" >/dev/null && echo "rmi $img"
done
echo "builder: $(docker builder prune -a -f 2>&1 | tail -1)"
journalctl --vacuum-size=500M 2>&1 | tail -1
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
