# LIVE PRODUCTION — DO NOT DELETE, MOVE OR "CLEAN UP"

This folder (`/root/claudecode/aicom` on factory-vps) is not scrap and not an old checkout.

- It is the compose project of the AI Factory (`aicom-app-1`, magic-ai-factory.com).
- Running containers bind files and folders from it: the factory backend (`data/`: secrets, admin users, store,
  pipeline state), the apex hub `modelmarket-hub` (deposit claims), `alien-monitor` (the UNI anvil chain),
  `ailottery-relayer-uni`, `argus`, `argus-uni`, `aicom-prometheus-1`, `aicom-grafana-1`, `aicom-data-keep-1`,
  and the `uni-journey` canary (`pov-demo/`).
- `du` shows it as several GB. That is live data, not reclaimable space.

On 2026-11-13 a disk-reclaim agent deleted it as "dated /root scrap (5G)". The factory answered 500 for 12 hours
and its admin said "Admin not configured" until it was restored from borg on 2026-11-14.

Protection now in place:
- `chattr +i` on `/root/claudecode` and `/root/claudecode/aicom` (top-level entries cannot be removed). Do not
  lift it to "finish a cleanup".
- `aicom-factory-guard` (systemd timers): an hourly copy in `/var/lib/aicom-factory-keep`, and a check every
  5 minutes that brings back missing files and restarts containers left bound to deleted paths.
  `journalctl -u 'aicom-factory-guard*'`, `aicom-factory-guard check`.

To free disk space on this host, use `aicom-disk-cleanup` or ask the owner. Never remove anything under `/root/claudecode`.
