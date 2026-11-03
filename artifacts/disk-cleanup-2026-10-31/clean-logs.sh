set -u
echo "before: $(df -h / | tail -1)"
journalctl --vacuum-size=500M 2>&1 | grep -i freed | tail -1
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
