set -u
echo "before: $(df -h / | tail -1)"
docker images --format '{{.Repository}}:{{.Tag}}|{{.CreatedAt}}' | awk -F'|' '($1 ~ /^(modelmarket-hub|signal-hunt-hub):/) && ($2 < "2026-10-01") {print $1}' > /root/cleanup-20261031-old-hub-tags.txt
echo "old hub tags (before 2026-10-01): $(wc -l < /root/cleanup-20261031-old-hub-tags.txt)"
removed=0; kept=0
while read -r ref; do docker rmi "$ref" >/dev/null 2>&1 && removed=$((removed+1)) || { kept=$((kept+1)); echo "kept $ref"; }; done < /root/cleanup-20261031-old-hub-tags.txt
echo "untagged: $removed, kept: $kept"
echo "builder: $(docker builder prune -a -f 2>&1 | tail -1)"
journalctl --vacuum-size=500M 2>&1 | grep -i freed | head -1
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
