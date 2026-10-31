"""Port the observed-seller lifespan task and migration 063 into a live pre-split package."""
import pathlib, sys

pkg = pathlib.Path(sys.argv[1])

def replace_once(path, old, new):
    text = path.read_text()
    n = text.count(old)
    if n != 1:
        sys.exit(f"{path.name}: anchor found {n} times: {old[:60]!r}")
    path.write_text(text.replace(old, new))

api = pkg / "api.py"
replace_once(api,
    "        deposit_task: asyncio.Task | None = None\n",
    "        deposit_task: asyncio.Task | None = None\n"
    "        observe_task: asyncio.Task | None = None\n")
replace_once(api,
    "        # Pay-on-Verified: re-queue verifications left pending by a previous process\n",
    "        # x402 sellers that consented to be listed from their own discovery document\n"
    "        # (observed_sellers.py, spec §2.7), re-read when due. With no consented seller a cycle\n"
    "        # is one query. Small writes on the app's own connection, like the deposit watch.\n"
    "        from aimarket_hub import observed_sellers\n"
    "\n"
    "        if observed_sellers.enabled():\n"
    "            async def _periodic_observe() -> None:\n"
    "                await asyncio.sleep(max(0.0, float(config.crawl_initial_delay_s)) + 30.0)\n"
    "                while True:\n"
    "                    try:\n"
    "                        summary = await observed_sellers.observe_due(db, hub_url=config.hub_url)\n"
    "                        if summary.get(\"observed\"):\n"
    "                            logger.info(\"observed sellers: %s\", summary)\n"
    "                    except asyncio.CancelledError:\n"
    "                        raise\n"
    "                    except Exception as exc:  # noqa: BLE001 - a bad cycle must never kill the loop\n"
    "                        logger.warning(\"observed sellers: cycle failed: %s\", exc)\n"
    "                    await asyncio.sleep(600.0 + random.uniform(0, 60.0))\n"
    "\n"
    "            observe_task = asyncio.create_task(_periodic_observe())\n"
    "        # Pay-on-Verified: re-queue verifications left pending by a previous process\n")
replace_once(api,
    "for task in (crawl_task, collect_task, sweep_task, openapi_task, deposit_task, a2a_sweep_task):",
    "for task in (crawl_task, collect_task, sweep_task, openapi_task, deposit_task,\n"
    "                         a2a_sweep_task, observe_task):")

mig = pkg / "migrations.py"
replace_once(mig,
    "def channel_ledger_versions() -> list[int]:",
    '''# 063: x402 sellers listed from their own discovery document, with consent (spec §2.7).
# Its own table, never `capabilities`: an observed route must not be searchable as a
# catalogue row, routable or re-exported, and keeping it out structurally (spec §2.6 (2))
# means a query that forgets a filter cannot leak it.
_register(63, "063_observed_sellers", """
    CREATE TABLE IF NOT EXISTS observed_sellers (
        origin TEXT PRIMARY KEY,
        name TEXT DEFAULT '',
        discovery_url TEXT DEFAULT '',
        allowed_routes_json TEXT DEFAULT '[]',
        pinned_pay_to TEXT DEFAULT '',
        consent_json TEXT DEFAULT '{}',
        created_at TEXT DEFAULT (datetime('now')),
        updated_at TEXT DEFAULT (datetime('now')),
        observed_at TEXT DEFAULT '',
        last_error TEXT DEFAULT '',
        routes_json TEXT DEFAULT '[]'
    );
""", """
    DROP TABLE IF EXISTS observed_sellers;
""")

def channel_ledger_versions() -> list[int]:''')
(pkg / "migrations.py.rej").unlink(missing_ok=True)
print("ported", pkg)
