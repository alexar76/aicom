# HISTOR out of memory: two malloc arenas (2026-11-08)

## What happened

The service process (`python -m histor serve` in `histor-histor-1`, admin-vps) was killed by the kernel at its
1 GiB memory limit six times:

- 2026-11-06 17:19:07Z and 19:28:58Z;
- 2026-11-07 02:14:39Z, 17:23:26Z and 18:40:01Z;
- 2026-11-08 03:49:41Z.

Each kill interrupted the crawl running at the time ("interrupted: the process restarted before the crawl
finished" in `/health`). The 11-08 kill came five hours after the last crawl had finished, while the process
served about one request a second, mostly server pages for crawlers.

## Why

At rest the process held ~700 MiB resident, almost all of it anonymous memory. Its `/proc/1/smaps` showed
**40 glibc thread arenas holding 528 MiB** (64 MiB-aligned heaps), with ~100 MiB elsewhere.

glibc gives nearly every thread its own malloc arena: up to 8 × 8 cores = 64 on this host. A freed block stays in
the arena of the thread that freed it. HISTOR runs many threads:

- the web threadpool (40 by default) for the synchronous endpoints;
- the crawl workers (12);
- the lookup pools.

So the heap kept the peak of every thread. Any burst on top of ~700 MiB crossed 1 GiB: a crawl worker may buffer
a 32 MiB answer.

## Fix (2026-11-08 08:24:06Z, no image change)

- `histor/docker-compose.yml` sets `MALLOC_ARENA_MAX: "${HISTOR_MALLOC_ARENA_MAX:-2}"`. The host's compose file
  was byte-identical to the repository's before this change.
- `HISTOR_MEM_LIMIT=1536m` in `/opt/histor/.env` (was `1g`) as headroom. The host had ~8.7 GB available.
- The container was recreated with `up -d --no-deps --no-build histor` while no crawl ran. It is on the same
  image `sha256:2ae7d08b…`, so the MOMUS binding is unchanged.
- Backup: `/root/histor-backups/mem-20261108.AqNoqrYd` (docker-compose.yml and .env).

## After (45 minutes, sampled every 2 minutes from outside, 08:24–09:10Z)

| | before (11-08 ~08:40Z, 5 h after a restart) | after, 1 min | after, 45 min |
|---|---|---|---|
| resident | ~700 MiB | 261 MiB | 292 MiB |
| glibc arenas | 40 (528 MiB) | 2 (127 MiB) | 2 (127 MiB) |
| other anonymous | ~100 MiB | 71 MiB | 76 MiB |

The arenas stopped at two and their size did not move. Resident memory grew 31 MiB in 45 minutes and was flat for
the last ten. No OOM kill and no restart in that time. The real test is the next daily crawl. The 5-minute sampler
meant for it was refused on the host (persistent timer), so it is checked by hand.

## Rollback

On admin-vps as root:

```
cd /opt/histor
B=/root/histor-backups/mem-20261108.AqNoqrYd
cp -p "$B/docker-compose.yml" docker-compose.yml
cp -p "$B/.env" .env
docker compose -p histor --env-file .env -f docker-compose.yml -f docker-compose.postgres.yml up -d --no-deps --no-build histor
```
