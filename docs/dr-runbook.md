# Disaster Recovery Runbook — AI Market Hub

## Scope

This runbook covers the AI Market Hub payment infrastructure: channels database, payment verification, contract state, and hub key material.

## RPO / RTO

| Component | RPO | RTO |
|---|---|---|
| Channels DB (SQLite) | 5 min (WAL) | 15 min |
| Hub signing key | 0 (immutable once generated) | 1 hour |
| Contract state (on-chain) | 0 (Base L1 finality ~2s) | N/A |
| Factory wallet journal | Last write | 5 min |
| Grafana dashboards | 24h | 1 hour |

## Backup Procedures

### Channels Database

```bash
# Automated: runs every 5 min via cron
./scripts/backup_channels.sh
```

Backup location: `data/backups/channels_$(date +%Y%m%d_%H%M%S).db`
Retention: 30 days local, 90 days off-region

### Hub Signing Key

```bash
# One-time backup at key generation
cp data/hub_signing_key data/backups/hub_signing_key.$(date +%Y%m%d)
# Store off-server immediately (1Password / AWS Secrets Manager)
```

**CRITICAL:** If this key is lost, ALL manifests and receipts signed by this hub are invalid. Federation peers must be re-announced. There is NO recovery without the key.

### Factory Wallet Journal

```bash
# Automated: every hour
cp data/factory_wallet.json data/backups/factory_wallet_$(date +%Y%m%d).json
```

## Recovery Procedures

### Scenario 1: Channels DB Corruption

1. Stop hub: `docker compose stop hub`
2. Restore latest backup: `cp data/backups/channels_YYYYMMDD_HHMMSS.db data/channels.db`
3. Verify: `sqlite3 data/channels.db "SELECT COUNT(*) FROM channels WHERE status='open'"`
4. Replay WAL if available: `sqlite3 data/channels.db "PRAGMA wal_checkpoint(TRUNCATE)"`
5. Start hub: `docker compose start hub`
6. Verify: `curl http://localhost:9080/ai-market/v2/stats/live`

### Scenario 2: Hub Signing Key Lost

1. Generate new key: restart hub (auto-generates if `data/hub_signing_key` missing)
2. Back up new key immediately
3. Re-announce to ALL federation peers: `POST /ai-market/v2/federation/announce`
4. Update `.well-known/ai-market.json` on all reverse proxies
5. Notify partners: new public key in federation manifest

### Scenario 3: Smart Contract Paused (Emergency)

1. Confirm pause: Tenderly alert or `cast call <contract> "paused()(bool)"`
2. Identify cause: check Forta alerts, on-chain event logs
3. If legitimate security incident:
   a. Freeze all channel operations: `docker compose stop hub`
   b. Audit ALL recent transactions via Basescan
   c. Identify affected channels from `data/channels.db`
   d. Contact affected users with on-chain proof of deposits
4. If false positive:
   a. Governance proposal to unpause via Gnosis Safe
   b. 48h Timelock wait
   c. Execute unpause

### Scenario 4: RPC Provider Outage

1. Alchemy down → auto-failover to QuickNode (configured in RPC router)
2. Both down → auto-failover to public Base RPC
3. All down → hub enters read-only mode:
   - Channel operations return `503 Service Unavailable`
   - Existing channels' state preserved in SQLite
   - No new channels can be opened
4. Recovery: RPC restored → hub auto-resumes, replays pending transactions

### Scenario 5: Database Disk Full

1. Alert triggers when disk > 85% (Grafana alert)
2. Immediate: `./scripts/cleanup_old_backups.sh` removes backups > 30 days
3. If still critical: migrate to larger volume
4. Prevent: daily disk usage check in CI

## Verification Drills

Run quarterly:

```bash
# 1. Backup integrity
sqlite3 data/backups/channels_*.db "PRAGMA integrity_check"

# 2. Key presence
test -f data/hub_signing_key && echo "OK" || echo "MISSING"

# 3. Restore test (to temp location)
cp data/backups/channels_*.db /tmp/restore_test.db
sqlite3 /tmp/restore_test.db "SELECT COUNT(*) FROM channels"

# 4. Contract connectivity
cast call $AIMARKET_ESCROW_EVM_ADDRESS "domainSeparator()(bytes32)" --rpc-url $BASE_RPC_URL
```

## Escalation

| Severity | Response Time | Escalation Path |
|---|---|---|
| P0: Contract paused, key lost, DB corruption | 15 min | On-call → ops lead → founder |
| P1: RPC outage, disk > 90% | 1 hour | On-call → ops lead |
| P2: Single channel issue, slow RPC | 4 hours | On-call handles directly |

## Contact List

Fill in before production:

| Role | Name | Signal/Phone | PGP Key |
|---|---|---|---|
| Ops lead | ___ | ___ | ___ |
| On-call #1 | ___ | ___ | ___ |
| On-call #2 | ___ | ___ | ___ |
| Founder | ___ | ___ | ___ |
| Auditor (retainer) | ___ | ___ | ___ |
