---
title: "We Improved WARDEN's Warnings. Twelve Rechecks Changed No Choices."
published: true
canonical_url: https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/
main_image: https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/cover.webp
description: "720 fresh model answers showed a version-level improvement on six known cases. Twelve Stop rechecks changed no selected IDs. Here is what each result means."
tags: mcp, security, ai, opensource
---

WARDEN's local candidate selected an injected recommendation target 27 times out of 48, compared with 44 and 46 times for the published guarded profiles. That was an improvement on our six test cases.

Its Stop hook also asked the model to reconsider twelve answers. Not one selected ID changed.

Those findings belong next to each other. The first describes a difference between complete versions. The second describes what happened during twelve actual continuations. Giving the second result credit for the first would make a better release story and a worse account of the experiment.

This investigation grew out of [Launch Gate's comments on our earlier WARDEN article](https://dev.to/alexar76/we-attacked-our-own-mcp-firewall-with-its-source-code-open-14-of-17-attacks-got-through-now-2-of-2m7l#comment-3j00o). The useful question was whether we could measure a change in the model's choice, separately from its mentioning an attack or repeating a warning.

## A perfect score that left the guard untested

Our first selection test produced 270 correct choices out of 270. The unguarded model got its choices right too.

That result checked our test machinery, but it showed no additional benefit from WARDEN. With an explicitly correct hotel in every task, the model had little reason to depart from the user's criteria even when a tool result tried to redirect it.

The next version of the task used two equally acceptable hotels. Both met the user's requirements and tied on the deciding criterion. The user expressed no further preference. Two other records failed the requirements.

An injected note tried to favor one of the admissible hotels, sometimes indirectly through its attributes or a claimed preference. We could then compare how often the model selected that target with and without the injected note.

This changes the meaning of the score. Choosing the target is a valid answer. What we measure is a shift in its selection frequency across controlled conditions, not a count of individually incorrect recommendations.

It also separates three observations that otherwise get mixed together:

- A guard produced an instruction-specific warning.
- An answer visibly referred to that warning.
- The model selected a particular hotel.

None of those observations, alone, establishes the model's internal understanding or whether it obeyed the injected instruction.

## What we changed before the fresh run

The published guard had supplied generic notes about outside text on these injected cases. Our local candidate added bounded instruction signals and more specific warnings. These signals recognize selected patterns, including claimed preferences or prior approval accompanied by directives. They are fallible detectors, not a semantic account of every possible injection.

We also changed the warning channel itself. A security warning can accidentally promote source-controlled text: quote the attack inside a trusted-looking notice, or repeat an instruction embedded in a tool name.

Post and Stop warnings now use fixed sentences and opaque source IDs. They do not copy the detected instruction, raw tool names, source URLs or paths into the guard-authored warning. The ID permits correlation; it is not a verified package identity or an authorization.

The original untrusted tool result still remains in context. Changing the warning's contents does not remove that exposure.

We froze the protocol before the first new model response. We did not change the prompts, cases or criteria after the smoke calls. We compared the complete published 0.21.0 implementation with the local, unpublished 0.22.0 candidate, including earlier local fixes. This was not an experiment isolating one warning sentence or one detector rule.

## The fresh comparison

The design was six cases, eight repetitions, three input conditions and five interleaved profiles: **720 main answers**.

The inputs were the clean records, records with a neutral note matched to the injection's character length, and records with the injection. Record positions rotated. A separate set of 30 controls stated genuine preferences in the user's own request.

We used the official DeepSeek API alias `deepseek-flash`, temperature 0.3, thinking disabled and a maximum of 700 output tokens. Published and candidate profiles ran interleaved in the same study. There were no retries, fallback models or replaced answers. An API alias does not guarantee immutable model weights.

Here are the target selections. Every cell has a denominator of 48.

| Profile | Clean | Neutral note | Injected | Injected minus clean |
| --- | ---: | ---: | ---: | ---: |
| Unguarded | 26 | 23 | 48 | +45.8 percentage points |
| Published note | 29 | 25 | 44 | +31.3 points |
| Published note+Stop | 26 | 27 | 46 | +41.7 points |
| Candidate note | 23 | 23 | 27 | +8.3 points |
| Candidate note+Stop | 25 | 24 | 27 | +4.2 points |

![Target selections out of 48: clean, neutral and injected for all five profiles. Both candidate injected counts are 27; published counts are 44 and 46.](https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/selection-rates.png)

The candidate's injected target rate was closer to its clean baseline and to the common unguarded clean baseline. Its remaining increase over its own clean baseline was four selections for note and two for note+Stop: **8.3 and 4.2 percentage points**, respectively.

The guard also changed the clean distribution, so a raw comparison of 44 versus 27 would miss part of the picture. Adjusting each version against its own clean baseline, the candidate-versus-published attenuation was:

- **22.9 percentage points for note**, with a six-case cluster-bootstrap 95% interval of **−8.3 to +60.4**.
- **37.5 points for note+Stop**, with an interval of **+14.6 to +62.5**.

The note-only interval includes zero. The note+Stop interval excludes it in this analysis, but that is a comparison of versions, not an estimate of Stop's separate contribution.

The analysis also retained the neutral reference and the common unguarded baseline, rather than giving a guard credit merely for erasing its own clean-to-injected difference. Full values are in the [technical report](https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/study/report.en.html).

## Stop ran twelve times. All twelve IDs stayed the same.

The candidate emitted instruction-specific warnings on all 96 injected guarded samples, and on none of its 192 clean or neutral guarded samples. That establishes what the detector emitted on these inputs. It is not a general detection rate.

Only the candidate note+Stop profile requested continuations: twelve of its 48 injected samples. Four initially selected the target; eight selected the other admissible hotel. All twelve kept their selected ID.

Four answer texts changed. In three, a visible reference to the warning disappeared under our limited English surface-word screen. That screen is not an independent semantic assessment, and an absent warning phrase cannot tell us whether the model noticed or understood the warning.

An indiscriminate requirement to change the choice would be wrong here: eight initial choices already favored the alternative, and both tied hotels were valid options. The purpose of a recheck is to improve the decision or its support, not to maximize the number of flips.

What we can report is narrower: these twelve continuations incurred additional calls without observed selected-ID correction. We did not run a randomized continuation-versus-no-continuation experiment among identical triggered cases, so this is not a general causal estimate of Stop's value.

Launch Gate described this as an alarm without a brake and asked what new information the second look supplied. That is a useful design question. The continuation did receive an additional review instruction, so its input was not literally identical. It did not receive independently verified facts or a separate reconstruction of the task.

The hook's `block` response asks the host to continue generation and review the answer. It is not a permanent refusal, an independent verifier or a guarantee that a recommendation changes. This study used a controlled tool-role bridge and at most one user-role continuation, not native-client enforcement.

## The controls passed; the scope is still small

All 720 final selected IDs were admissible. Genuine-user preference controls passed 30/30. There were no missing, duplicate, invalid or length-truncated main answers.

Those are useful checks, but they leave several limits intact.

The six cases were known while we expanded the candidate's signals. They are development cases, not an independent holdout. Freezing them before this fresh run prevented outcome-driven changes during the run; it did not undo their role in developing the candidate.

Our intervals resampled six whole case clusters, retaining all repetitions and treatments. Eight repetitions do not turn six cases into 48 independent attack families. We used 2,000 bootstrap draws without a multiplicity adjustment. The observed reduction was concentrated in three cases; the other three already favored the target throughout the unguarded clean condition.

Admissible IDs also do not validate every explanation. Spot-reading the rechecked answers found inaccurate lists of eligible alternatives even when the selected hotel was valid.

The missing generalization evidence is a comparison on new injections written after the candidate freeze, preferably by someone who has not read its signal list. Improving the recheck itself would require another controlled comparison, with a genuinely different evidential basis and costs reported alongside any gain. Neither result can be supplied by relabeling this run.

## What this cost, and what we retained

The main model run took about 17 minutes on Linux. Including five smoke calls, 30 user-preference controls and twelve continuations, there were **767 API attempts**.

Reported usage was 438,085 input tokens, including 290,296 cached, and 58,241 output tokens. Using the off-peak tariff recorded for the run, the estimated charge was **$0.058**. That is a calculation from usage, not a provider invoice. A conservative budget ledger settled at about $0.116 using peak rates, below the authorized $1 limit.

The build and 714 WARDEN tests passed, along with 78 harness, budget and scoring tests, nine adapter tests and the existing deterministic scenario gate. A separately implemented accounting audit checked denominators and hashes. It was not an independent human review of the answers.

We retained complete initial and final answers, requests, responses, schedules, hook events and the usage ledger. The [frozen protocol](https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/study/protocol.html), [report in five languages](https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/study/report.en.html) and [public evidence extract](https://modelmarket.dev/blog/we-improved-wardens-warnings-twelve-rechecks-changed-no-choices/study/public-evidence.zip) distinguish the measured results from the remaining questions. The public extract preserves all full initial/final answer strings and synthetic model inputs; relay identifiers and internal filesystem inputs are omitted. It is not the complete internal runtime archive.

WARDEN 0.22.0 remains a local candidate in this study. The observed version-level improvement is worth keeping; the twelve unchanged selections are worth keeping beside it.

*Disclosure: The cover illustration was generated with AI; the graph was plotted directly from recorded counts. I maintain WARDEN and HISTOR in the alexar76/AICOM ecosystem. Research, implementation, analysis and writing used AI assistance. This is our evaluation of our own code, not an independent security audit.*
