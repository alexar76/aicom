# modelmarket.dev: readable route links on /examples and /developers — 2026-10-31

Owner: «Да, выкатывай». Code: aicom d6c3e6c8d (`aimarket_hub/landing.py`: the "Developers · Integration examples"
paragraph under "Choose your route" gets `class="section-note"`, the site's cyan links; bare, the links took the
browser's default blue, rgb(0,0,238) on rgb(2,3,10), about 2.2:1; now rgb(56,224,255), about 13:1).

Apex hub on factory-vps only. The running image `aicom-security:modelmarket-hub-python-20261031` (3b80328949ed) had
main's previous `landing.py` byte for byte, and the service imports `/app/aimarket_hub` (`python -m aimarket_hub serve`
from /app; the site-packages copy is shadowed). Overlay `modelmarket-hub:examples-links-20261031` = that image +
landing.py (`Dockerfile`, `build.sh`); `smoke.py` ran inside it with no network: file hash, the app imports, both
pages in all five languages carry the section-note links. Rolled at 18:43Z with
`/root/hub-3160-main-20261021/roll.sh` (SQLite backup `/app/data/hub-backup-pre-3160-20261031T184302Z.db`,
rollout_container.py with health on :9083 and THEMIS :9460): healthy, THEMIS recreated and healthy.

Verified live: both pages serve `<p class="section-note">` in EN and RU, the links compute to rgb(56,224,255) in a
browser, /ai-market/v2/health 200.

Rollback: previous container `modelmarket-hub-security-prev-1793472183687974477` (+ `themis-security-prev-1793472183687974477`)
via rollout_container.py, or roll again onto `aicom-security:modelmarket-hub-python-20261031`. The other five hubs
serve the same pages and get the fix with their next rollout.
