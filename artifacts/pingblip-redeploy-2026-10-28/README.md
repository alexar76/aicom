# PingBlip production redeploy — 2026-10-28

Forge, the game and World were rebuilt and restarted successfully. Runtime source corresponds to `27dd35d785935a1938f18d375eb56214ee6e3aad`; the initial asset archive was `adea1f8a197d4e9badfed559b960518bd1449cf4`. The metadata-only follow-up was synchronized before the game and World builds, which is why the build log ends with the earlier archive ID. Production environment, persistent volumes and the existing healthy PostgreSQL container were retained. Previous application images were tagged `:prev` before building.

Updated figures: Spark Moth, Rust Crown, Winged Bolt, Cola Cube, Caramel Bust, Graveyard Shift and Taxi Larva. Social image metadata now includes the model content hash to give each revised sculpt a fresh OG/Twitter image URL.

| Live verification | Result | Evidence |
| --- | --- | --- |
| All 80 roster models, six eye variants and supported preview copies; plain and versioned model URLs | 745/745 URLs match local SHA256, length, MIME and origin | [Asset report](live-assets.json) |
| Game and World OG/Twitter metadata | 160/160 pages advertise current model versions | [Social preview report](live-og-verification.json) |
| Rendered OG images for the seven revised figures | 14/14 PNGs are 1200×630 and match the new JPEGs over archived previous JPEGs | [Social preview report](live-og-verification.json) |
| Browser renders, shelf/pack previews and share links | 33/33 content checks pass; 47 screenshots | [Browser summary](browser-smoke-summary.json) |
| Compiled game model versions | All 80 hashes match | [Browser summary](browser-smoke-summary.json) |
| Public HTTPS pages and game service worker | All HTTP 200 | [HTTPS health](https-health.json) |

One optional external Telegram script request produced a browser socket error on the Forge Spark Moth check. The same external endpoint returned HTTP 200 in an independent HEAD probe; the selected model, hash and render all passed. There were no uncaught application runtime errors. The browser verifier initially used asynchronous WebGL readback on a game canvas configured with `preserveDrawingBuffer=false`; focused retries used compositor screenshots and passed. Original and retry evidence remain available.

[Release receipt](release-summary.json) records running image digests and inputs. [Build/deploy log](build-and-deploy.log), [initial synchronization](rsync.txt) and [metadata synchronization](metadata-rsync.txt) preserve operational evidence. Raw command output and the system verification patch intentionally retain original whitespace. Browser verification blocked mutating requests locally and used fresh contexts; checks did not create gameplay data or publish social posts.
