# User Cases: Creator Algorithm Coach

## Case 1: TikTok Creator Optimizing Posting Time

**User**: Maya, 24, cooking content creator with 85k TikTok followers

**Problem**: Maya's views dropped 40% over two weeks. Her 3 PM posting time suddenly stopped working. She knows TikTok's algorithm shifted but can't figure out what changed.

**Solution with Creator Algorithm Coach**:

1. **Launch the app** and select TikTok as active platform, "cooking" as niche
2. **Navigate to Discover** and find "Optimal Posting Times — TikTok Cooking Niche" capability
3. **Purchase a signal call** for \$0.15:
   ```dart
   // The app does this automatically on "Buy"
   final result = await agent.invoke(
     capabilityId: 'tiktok-optimal-times-cooking-v3',
     input: {'platform': 'tiktok', 'niche': 'cooking'},
     channelId: channel.id,
   );
   // result.output: {
   //   "optimal_posting_time": "14:14 EST",
   //   "confidence": 0.89,
   //   "secondary_window": "19:30-21:00 EST",
   //   "tee_receipt": {...}
   // }
   ```
4. **Dashboard updates** with new signal: "Optimal posting time: 2:14 PM EST (shifted from 3:00 PM)"
5. **Schedule next video** for 2:14 PM EST

**Result**: Maya's next video hits 340% average watch time and gets pushed to FYP within 2 hours. Revenue from that video: \$180 in brand bonuses.

**Why marketplace?** A centralized SaaS would still show Maya "3 PM is best" from a month-old analysis. The marketplace's Tier 3 decay (weekly refresh) caught the shift within days of the algorithm change.

---

## Case 2: YouTube Channel Tracking Algorithm Shifts

**User**: David, 32, tech reviewer with 240k YouTube subscribers

**Problem**: David's CTR dropped from 12% to 6% over a week. His thumbnails didn't change, his topics didn't change, but YouTube stopped pushing his videos in search recommendations.

**Solution**:

1. **Open the Algorithm Shift Detector** capability in the app
2. **Buy a \$0.30 signal call** targeting YouTube's search ranking changes
3. **Receive alert**: "YouTube search ranking weights recalculated — CTR now less weighted than watch-session depth for first 48 hours"
4. **Insights Timeline** shows: May 15 — YouTube algorithm shift detected (High impact)
5. **Adjust strategy**: Make first 30 seconds of videos longer and denser to boost watch-session depth metric
6. **Buy Hook & Structure Benchmarks** (\$0.20) to see which opening patterns drive retention in tech niche

**Result**: David's CTR recovers to 9.5% within 4 days. He attributes the quick recovery to knowing *exactly* what changed, rather than guessing.

**Why marketplace?** YouTube's algorithm shift was detected by Platform Signals Inc., a specialist that monitors YouTube's ranking changes by analyzing thousands of channel performances daily. That specialist's data is now available to David through the marketplace — no multi-thousand-dollar monthly SaaS subscription needed.

---

## Case 3: X/Twitter Growth Hacker A/B Testing Hooks

**User**: Priya, 26, growth marketer managing 12 brand accounts on X

**Problem**: Priya needs to A/B test hook structures across accounts but can't tell which hooks are genuinely performing vs. getting lucky. Platform analytics are too noisy and gated behind 7-day delays.

**Solution**:

1. **Set up the app** with X/Twitter platform, "marketing" niche
2. **Buy "Hook Conversion Benchmarks — X** capability (\$0.20/call)
3. **Paste her own metrics** into the app — her posting times, engagement rates, hook structures
4. **The app runs her data through a TEE-attested capability** (simulated in dev; real enclave in production) that:
   - Normalizes her metrics
   - Compares against marketplace benchmarks
   - Returns verified hook conversion rates
5. **Get attestation-verified results** (TEE simulation in current release):
   ```json
   {
     "hook_type": "pattern_interrupt",
     "conversion_rate": 0.72,
     "benchmark_avg": 0.54,
     "sample_size": 340,
     "tee_verified": true
   }
   ```
6. **Sell her anonymized metrics** back to the marketplace for \$0.12 per data point — other creators can buy her real-world hook data knowing it's TEE-proven

**Result**: Priya identifies "pattern interrupt" hooks as 33% above benchmark in the marketing niche within 24 hours. She rolls this structure across all 12 accounts. Weekly engagement increases 22%.

**Why marketplace?** The two-sided marketplace means Priya isn't just consuming data — she's also earning from her real-world performance. The TEE attestation ensures buyers trust her data, which means higher prices and faster sales. A centralized SaaS can't offer this because it has no way to verify seller honesty.
