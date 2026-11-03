set -u
echo "before: $(df -h / | tail -1)"
cd /var/backups/histor
for f in histor-20261025T035327Z.dump histor-20261026T181252Z.dump histor-20261027T035237Z.dump histor-20261028T084932Z.dump; do
  [ -f "$f" ] && rm -v "$f"
done
echo "kept dumps: $(ls histor-*.dump | tr '\n' ' ')  keys tars: $(ls keys-*.tar | wc -l)"
rm -rf /var/backups/histor-v13-20261010 && echo "removed /var/backups/histor-v13-20261010"
rm -fv /root/dioscuri-tree-pre-20261017.tgz
cd /var/tmp
for p in warden-0170-build warden-0170-dist warden-0170-dist2 warden-0170-label warden-0180-dist warden-0190-build warden-0190-dist warden-0190-label \
         warden-0200-build warden-0200-label warden-0210-build warden-0210-label warden-0220-build warden-0220-label warden-0221-build warden-0221-label \
         histor-warden-446c2135f histor-warden-446c2135f.tar histor-warden-operator-build-446c2135f.py histor-warden-operator-deploy-446c2135f.py \
         histor-warden-release-446c2135f histor-warden-verify-446c2135f.py histor-warden-metadata-231c6b061 histor-warden-metadata-4afe02438 histor-warden-metadata-ce1dd74ed \
         warden-screen-40d5f73.bundle warden-screen-421fb2c.bundle warden-screen-a635f19.bundle warden-screen-image-probe.mjs warden-screen-native-build-current-base.py \
         warden-screen-native-build.py warden-screen-native-deploy-current-base.py warden-screen-native-deploy.py warden-screen-native-verdict.py warden-screen-production-verify.py \
         warden-screen-release-a635f19 warden-screen-release-a635f19-current-base warden-screen-release-a635f19.git; do
  [ -e "$p" ] && rm -rf -- "$p" && echo "removed /var/tmp/$p"
done
for img in praxis:momus-18e20e76b526 praxis:momus-c946cfacf2f6 praxis:momus-a442460d16e3 praxis:momus-47c9e1fd8a39 praxis:momus-7105cc2e5778 warden:metadata-diagnostic-ce1dd74ed; do
  docker rmi "$img" >/dev/null 2>&1 && echo "rmi $img" || echo "kept $img (in use or absent)"
done
echo "dangling: $(docker image prune -f 2>&1 | tail -1)"
echo "builder: $(docker builder prune -f 2>&1 | tail -1)"
apt-get clean && echo "apt cache cleaned"
echo "after: $(df -h / | tail -1)"
