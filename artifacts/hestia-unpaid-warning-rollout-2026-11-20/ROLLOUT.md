# HESTIA warns about priced agents with no payout address — rollout 2026-11-20

Owner 20.11: «Пустой адрес выплат». Code: aicom main 890b60970 (hestia/payout.py, deploy warnings,
unpaid_reason on /v1/hearth, /v1/tenants, /v1/owners/me; both deploy tools print them; docs in five languages).

Checks before: hestia 829 passed (6 new tests), hestia-agents test_cli as before (1 old failure). Open alerts:
only host_disk[attested]. Hearth only: the runner is unchanged.

| container | switched (UTC) | new image | previous (rollback) |
|---|---|---|---|
| hestia-hestia-1 | 18:35:38 | aicom-security:hestia-hearth-unpaid-20261120 = 49d5114aad9c | hestia-hestia-1-security-prev-1795199739224281078 (73770388103e) |

Ledger dump: /root/hestia-backups/hestia-pg-pre-unpaid-20261120T183538Z.sql.gz. Rollback:

    cd /root/hestia-unpaid-rollout-20261120 && python3 rollout_container.py hestia-hestia-1 --rollback

After: 19 running; the roster marks exactly one agent, blackwell-storefront ($0.001, no address, no hub
chosen): "every call is served free…". 13 priced agents with an address carry no mark; an unpaid call to
id-check still answers 402; aid-discover proven_bound; no traceback in the hearth log.
