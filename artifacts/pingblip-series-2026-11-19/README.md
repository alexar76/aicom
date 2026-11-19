# PingBlip Shorts, 24–26 November 2026

PB88–PB93 use fresh turntable renders from nine PingBlip game models. Each day pairs a character reveal with a two-character choice. The early slot alternates between the two formats.

The Blender renderer records the figure plates in `work/`. The compositor assembles eight-second 1080 × 1920 Shorts at 30 fps and uses the existing PingBlip soundtrack. The render log, visual contact sheets, media checks, YouTube snapshots and publication state are in `qa/`. The final media, model hashes, preview, publication plan and receipt are in `../PromoMaterials/blip/youtube-season-something-pinged/v23-bench-matchups/` relative to the workspace root.

`publish.py` records accepted YouTube IDs before further network writes. Review `qa/publication-state.json` before resuming an interrupted upload. Schedule verification checks the saved IDs against the six requested UTC slots.
