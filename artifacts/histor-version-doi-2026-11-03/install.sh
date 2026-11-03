#!/bin/bash
# admin-vps: the /datasets/ page cites each snapshot by its own Zenodo version DOI (2026-11-03).
# Copied next to this script: dataset_index.py, zenodo_reminder.sh, export_dataset.sh (aicom histor/).
# The installed copies equalled main before this change (sha256 checked 2026-11-03 15:46Z).
#
# Rollback: T=pre-versiondoi-20261103; B=/root/histor-backups
#   cp -p $B/dataset_index.py.$T /usr/local/lib/histor-dataset/dataset_index.py
#   cp -p $B/histor-zenodo-reminder.$T /usr/local/sbin/histor-zenodo-reminder
#   cp -p $B/histor-export-dataset.$T /usr/local/sbin/histor-export-dataset
#   cp -p $B/datasets-index.html.$T /var/lib/histor-datasets/index.html; rm -f /var/lib/histor-datasets/zenodo.json
set -euo pipefail
cd "$(dirname "$0")"
B=/root/histor-backups; T=pre-versiondoi-20261103; DIR=/var/lib/histor-datasets
mkdir -p "$B"
[ -e "$B/dataset_index.py.$T" ] || cp -p /usr/local/lib/histor-dataset/dataset_index.py "$B/dataset_index.py.$T"
[ -e "$B/histor-zenodo-reminder.$T" ] || cp -p /usr/local/sbin/histor-zenodo-reminder "$B/histor-zenodo-reminder.$T"
[ -e "$B/histor-export-dataset.$T" ] || cp -p /usr/local/sbin/histor-export-dataset "$B/histor-export-dataset.$T"
[ -e "$B/datasets-index.html.$T" ] || cp -p "$DIR/index.html" "$B/datasets-index.html.$T"
bash -n zenodo_reminder.sh; bash -n export_dataset.sh; python3 -I -m py_compile dataset_index.py
install -m 0644 dataset_index.py /usr/local/lib/histor-dataset/dataset_index.py
install -m 0755 zenodo_reminder.sh /usr/local/sbin/histor-zenodo-reminder
install -m 0755 export_dataset.sh /usr/local/sbin/histor-export-dataset
python3 -I /usr/local/lib/histor-dataset/dataset_index.py --zenodo "$DIR"
echo "zenodo.json:"; cat "$DIR/zenodo.json"
grep -q 'https://doi.org/10.5281/zenodo.23884408' "$DIR/index.html" && echo "page cites the 2026-11-02 version DOI"
grep -q 'doi:10.5281/zenodo.23512760' "$DIR/index.html" && echo "page lists the 2026-10-20 version DOI"
/usr/local/sbin/histor-zenodo-reminder --dry
echo DONE
