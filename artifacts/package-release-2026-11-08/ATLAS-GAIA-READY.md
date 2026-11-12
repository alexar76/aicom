# ATLAS 0.4.0 and GAIA 0.3.0: no longer on hold (2026-11-08)

This replaces the "hold" rows and the "Hold" section of `README.md` in this folder. That README is not edited here,
because another session has an uncommitted change to it in the main checkout.

**Fixed in `694f30f3b`.** The mesh and extra-sensor modules read `config/*.yaml` from the repository layout only, so
`import atlas.main` failed from any pip install (aimarket-atlas 0.3.5 on PyPI too), and GAIA's two mesh modules did
the same. Both wheels now carry the catalogs: GAIA in `gaia/_config/` through hatch `force-include` from
`gaia/config/`, and ATLAS in `atlas/atlas/_config/`, kept equal by `scripts/sync_physical_sensor_catalogs.sh`. The
modules read the packaged copy when the repository's is absent.

The files in `pypi/` (`aimarket_atlas-0.4.0*`, `aimarket_gaia_gateway-0.3.0*`) were rebuilt from a clean export of
`694f30f3b`; `SHA256SUMS` lists them.

| Check | Result |
|---|---|
| Wheels against the commit | GAIA 96 files, ATLAS 87, all equal the commit (GAIA's `_config/` equals `gaia/config/`) |
| Secret gate | both wheels and both sdists clean |
| Fresh venv, Python 3.12, dependencies from PyPI | every module imports: GAIA 89, ATLAS 48 including `atlas.main`. The catalogs load from `_config/`: 50 Open-Meteo cities, 30 Sensor.Community cities, 80 extra sensors |
| GAIA installed from its sdist | the same: 89 modules, catalogs from `_config/` |
| Full suites | ATLAS 732 passed. GAIA 942 passed, 22 failed: 21 are the GAIA+hub end-to-end fakes without the hub's `oracle_paid` argument (failing on main before this change too), and `test_memtrace`'s process-wide allocation threshold (492,702 of 500,000), which passes alone 3 of 3 |
| New tests | `gaia/tests` and `atlas/tests` `test_packaged_catalogs.py` load each module from a site-packages-like layout. They fail on the previous modules and pass now. `tests/test_packaged_sensor_catalogs.py` checks the copies and both packaging configs |

Both are ready to upload with the other ready packages:

```
uvx twine upload artifacts/package-release-2026-11-08/pypi/aimarket_atlas-0.4.0*
uvx twine upload artifacts/package-release-2026-11-08/pypi/aimarket_gaia_gateway-0.3.0*
```
