# Jury of three or jury of five — measured

> 🌐 **English** · [Русский](jury-3-vs-5.ru.md) · [Español](jury-3-vs-5.es.md) · [Français](jury-3-vs-5.fr.md) · [中文](jury-3-vs-5.zh.md)

Same 24 checks (12 tasks × an honest and a subtly wrong answer: factorization, sorting, a sum,
miles → km, days between dates, required JSON fields, counting vowels, reversing a string, a
primality question, a translation, a capital city) sent once through the five-seat Metis jury on
2026-10-03. Smaller juries are computed from the same per-juror votes with the jury's own rule
(strict majority of the whole roster, abstention = no vote, score = agreement × median confidence,
0.7 bar), so only the roster differs. Script: [`metis/bench/jury_3v5.py`](https://github.com/alexar76/metis/blob/main/bench/jury_3v5.py);
raw votes: [`metis/bench/results/2026-10-03-jury-3v5.json`](https://github.com/alexar76/metis/blob/main/bench/results/2026-10-03-jury-3v5.json).

| Roster | Right decisions | Undecided | Wrong decisions | Wait, median / slowest (s) |
|---|---|---|---|---|
| 3 seats, one lineage (DeepSeek, MiniMax, GLM) | 20/24 | 4 | 0 | 7.1 / 52.4 |
| 3 seats, three lineages (DeepSeek, Claude, Mistral) | 16/24 | 8 | 0 | 3.7 / 29.2 |
| 5 seats (all) | **21/24** | **3** | **0** | 7.1 / 52.4 |

| Juror | Wrong votes of 24 |
|---|---|
| Claude Sonnet 5.5 (Anthropic) | 0 |
| DeepSeek V4 Pro | 1 |
| GLM-5.3 (Zhipu) | 1 |
| MiniMax M3 | 2 |
| Mistral Medium 3.5 | 6 |

**What it shows**

- **No roster made a wrong decision.** Disagreement leaves a verdict undecided (buyer refunded,
  seller not blamed); it never flips it.
- **Five seats decide most often** (21/24): one wrong vote no longer blocks a verdict.
- **Diversity only helps if every juror is strong.** The three-lineage trio did worst (16/24)
  because Mistral Medium 3.5 voted wrong 6 times — mostly accepting wrong answers (a sum off by one,
  a wrong factor, a wrong vowel count, "97 is not prime"). In a five-seat jury the others outvote it;
  in a three-seat jury it blocks every decision it disagrees with.
- The slowest juror sets the wait: GLM-5.3 took up to 52 s on a hard factorization; Claude and
  Mistral never above 9 s.

**Caveats.** 24 checks, one run, checkable tasks only; one task (JSON fields) is arguably ambiguous
— its honest answer invents an e-mail address, and two jurors objected. Treat these numbers as
indicative, not as a ranking.

**Next step.** Replace the Mistral Medium seat with a stronger model of a different lineage
(for example Mistral Large or Gemini) and re-run the same 24 checks: the script makes that a
two-minute comparison.

## Replacing the weak seat (same day)

| Candidate for the fifth seat | Wrong votes | Abstentions | 5 seats right | Verdict |
|---|---|---|---|---|
| Mistral Medium 3.5 | 6 / 24 | 0 | 21/24 | weak: accepted wrong answers |
| Mistral Large 2512 | 1 / 2 answered | 22 (`rate_limit` at the provider) | 20/24 | unavailable: a juror that cannot answer abstains |
| **Gemini 3.8 Flash** | **1 / 24** | **0** | **22/24** | **kept** (also 22/24 as the three-lineage trio DeepSeek + Claude + Gemini) |

Each candidate ran the same 24 checks with fresh audit ids; raw votes are in `metis/bench/results/`. Two lessons: **measure a juror before trusting it** (a strong-sounding model can be the weakest vote), and **availability is part of quality** — a rate-limited juror is an abstention on every busy minute. The roster lost its European lineage with this swap; it now spans Chinese (DeepSeek, MiniMax, GLM) and US (Anthropic, Google) labs. Between runs the same trio moved by one decision (20 → 21/24): with 24 checks, a difference of one is noise.

## Retest: Mistral with reasoning switched on

The first verdict on Mistral Medium 3.5 was suspicious: it answered in about a second while the
others thought for 3–50 s, so it may have lost to the *mode*, not the model. Metis jurors gained
`extra_body` (merged into every request; it cannot replace the model or the messages) and Mistral
was re-run as a sixth seat with OpenRouter's `reasoning: {effort: medium}`, then `{effort: high}`.

| Mistral Medium 3.5 | Wrong votes | Median answer | Output tokens |
|---|---|---|---|
| no reasoning | 6 / 24 | 1.1 s | — |
| `reasoning: medium` | 7 / 24 | 1.2 s | ~105 |
| `reasoning: high` | 6 / 24 | 1.1 s | ~100 |

The switch works — asked a short question directly, the same model spent 273–2143 tokens
reasoning — but inside the jury, where the answer must be one strict JSON verdict, it barely
thinks even at `high`, and keeps accepting wrong answers. A juror that does not recompute is a weak
juror for computation, whatever its benchmark reputation. **Decision: Gemini 3.8 Flash keeps the
fifth seat; Mistral is out.**

**Correction to the tables above.** The task "how many days are there from 2026-01-01 to
2026-03-14?" was ambiguous: counting both ends gives 73, the "wrong" answer, and five jurors
accepted it. It is now asked as "how many days after 2026-01-01 does 2026-03-14 fall?". Leaving
the original pair out, no roster in any run made a wrong decision. On the reworded set the final
roster — DeepSeek, MiniMax, GLM, Claude, Gemini — decides **23 of 24, none wrong**; the trio
DeepSeek + Claude + Gemini decides 22 of 24 with the shortest wait (5.4 s median).
