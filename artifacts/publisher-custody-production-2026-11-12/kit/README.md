# Publisher custody rollout kit

The overlay is limited to twenty custody files from the current workspace. It uses the 3.21.0 source baseline `ce215c70b` for the sixteen replaced files. Before building, `prepare` compares those files to their baseline hashes in both the running container and the exact parent image. The candidate preserves the other files and installed packages in that image.

```sh
stage_dir=$(mktemp -d /private/tmp/modelmarket-publisher-custody-XXXXXXXX)
python3 artifacts/publisher-custody-production-2026-11-12/kit/stage.py "$stage_dir"
```

Stage the resulting directory on `factory-vps`. `bash deploy.sh prepare` builds with Docker networking disabled and runs the new and previous images on disposable copies of both SQLite ledgers. The checks compare migration versions and pre-existing table row counts, exercise capture replay on synthetic credits, and verify Hub health and withdrawal route registration. The previous image starts on the migrated copies to exercise code rollback.

`bash deploy.sh switch <public-payout-sender>` takes fresh SQLite snapshots into a root-only backup directory, then uses the existing container switch helper with the Hub and THEMIS health checks. The public sender is the sole optional environment change. The key and signer worker are operated separately. `bash deploy.sh rollback` restores the previous image and clears the new sender setting, keeping the forward-compatible database schema and transaction history. The saved database copies are evidence and disaster recovery inputs. Keep the live ledger after a canary makes an on-chain transfer.
