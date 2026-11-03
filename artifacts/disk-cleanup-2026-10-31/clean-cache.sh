set -u
echo "before: $(df -h / | tail -1)"
echo "running builds: $(pgrep -fa 'docker build|buildx' | grep -v pgrep | wc -l)"
echo "builder: $(docker builder prune -a -f 2>&1 | tail -1)"
echo "dangling: $(docker image prune -f 2>&1 | tail -1)"
journalctl --vacuum-size=300M 2>&1 | grep -i freed | head -1
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
