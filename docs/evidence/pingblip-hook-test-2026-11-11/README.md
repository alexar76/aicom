# PingBlip Shorts hook comparison

Compare a Short that opens on the weather-based reveal with one that opens on the first feed. Use two new Shorts each day for four days. Each hook runs twice at 13:00 UTC and twice at 19:00 UTC. Keep similar subjects within each daily pair and match the duration, subtitle style, audio level and final call to action. Use actual game footage for both hooks. Each edit gets its own episode link.

PB82–PB89 are candidates for 21–24 November. The native queue captured on 10 November had 20 entries and ended with PB81 on 20 November at 19:00 UTC. The proposed IDs were absent from the saved native snapshot, series plan and upload log. Before assigning files or dates, refresh those records and check for occupied slots and reused IDs. If the queue has grown, move the entire block to the next four consecutive days with both slots free. Use the same order and recheck attribution IDs. [Experiment plan](plan.json) · [Native queue verification](../../../artifacts/pingblip-series-2026-11-10/qa/youtube-verification.json)

## Baseline from 24 October

The 05:47 UTC snapshot included 37 public Shorts in 43 video rows. Those public Shorts had 4,838 lifetime views. Five Shorts accounted for 19 video-attributed browser profiles in the rolling acquisition window. None had hatched or fed a pet by the snapshot. Across sources, the snapshot excluded 17 marked test profiles. The itch.io and CozyGamesDB groups each had one profile and one hatch, with zero first feeds. View and acquisition windows differ, so these counts provide separate baselines. [Saved funnel snapshot](../../../../PromoMaterials/blip/growth/latest-funnel.json)

## What to record

1. Keep the clickable channel-profile link and the final on-screen prompt consistent across the block. Add each existing `/go/pbNN` URL in the same place in its Short. That redirect stamps `youtube / shorts / get-your-pet / pbNN`. Viewers can type or copy it. Shorts descriptions and comments render URLs as plain text. Clicks on the channel-profile link remain a channel-level cohort. [YouTube link behavior](https://support.google.com/youtube/answer/13748639?hl=en) · [PingBlip attribution](https://github.com/alexar76/pingblip/blob/main/docs/PLAYER-FUNNEL.md)
2. In Studio, record **Stayed to watch** by video for the first seven Pacific reporting dates including publication day. Record **Shown in feed** and **Engaged views** for the same range. Wait for that date range to populate and use JSON `null` for any metric that is still unavailable. The two UTC slots provide different exposure on the first reporting date. The plan gives each hook equal representation in both slots. [Shorts metric definitions](https://support.google.com/youtube/answer/12220281?hl=en) · [YouTube reporting dates](https://developers.google.com/youtube/analytics/dimensions)
3. Before the block starts, confirm the experiment IDs have no existing groups in the game funnel. For each Short, save the aggregate JSON from the authenticated read-only `GET /api/admin/funnel` at 168 hours after the verified native slot, within 30 minutes. Name the file `pbNN.funnel.json`. If the actual releases disrupt the slot balance, record the deviation before interpreting the comparison. The endpoint excludes marked tests and recognized automation from groups. Matching groups count first-touch browser profiles. D1 return and D1 feed use the next UTC calendar day after first hatch and the denominator `returnEligible`.
4. Enter the Studio observations as a JSON object keyed by episode. Each entry needs the actual YouTube `videoId`, inclusive `startDate` and `endDate` in `YYYY-MM-DD`, and the three metrics named in the plan. Use a percentage on the 0–100 scale for `stayedToWatchPercent`. Use counts for `shownInFeed` and `engagedViews`. Keep credentials and cookies out of the data files.

## Compare the results

From this directory, run:

```bash
python3 compare.py plan.json snapshots studio.json
```

The report gives the difference in percentage points between the weather and feed hooks for each day and slot. It gives the equally weighted mean when all four pairs have Studio data. It also totals the episode-tagged visits, ready screens, hatches, first feeds and eligible returns for each hook. Use `visits` as the denominator for ready screens and hatches, `hatched` for first feeds and `returnEligible` for next-day outcomes. A zero denominator leaves the rate undefined. A single profile may see multiple Shorts, and a small cohort will move by large percentages when one player acts.

Choose a hook to repeat if it leads on most paired days and the direction also holds in both slots. Treat low feed exposure, missing Studio data, or opposing slot results as a reason to collect another balanced block. The experiment measures the first-frame choice with the available channel data. The tagged game outcomes show whether anyone followed the episode route and played.
