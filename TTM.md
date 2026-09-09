# TTM — John Carter's Squeeze: status, results & backlog

> Living handoff doc. **Last updated: 2026-09-09** (Claude Code).
>
> **WHERE IT STANDS.** TTM is **a book leg, never a standalone.** The crown cell earns about $2,900
> a year on one contract — too small to trade by itself — but its daily profits are uncorrelated
> with both NQ crowns (0.060 to ORB, 0.003 to ENGU-Q), and three ES contracts of it on the house
> baseline lifted the book. The owner adopted it on 2026-09-08 and **swapped the book leg onto the
> validated tilted version on 2026-09-09**.
>
> - Paper legs: **`TTM_299_T`** (the book leg, from 2026-09-10) and **`TTM_299`** (its exact matched
>   control, from 2026-09-09). The nightly report's `book` figure = ORB 234 + ENGU-Q 309 at one NQ
>   contract each **+ three ES contracts of `TTM_299_T`**.
> - Crown cell, unchanged since run #299: **ES 30m RTH**, Keltner 1.5, stop 1.5 ATR, no entries in
>   the last bar, hourly verification length 20 — `TTMSQZ_3_0_ES30N.py`.
> - Validated improvements, in order: **run #340**, the deep-squeeze 1.5x size tilt (same trades, 1.5
>   contracts on the 188 of 359 entered while the hourly compression ratio is at or under 0.85) — this
>   is the leg the book carries; and **run #353**, the STRUCTURAL STOP, which passed every gate and
>   cleared every clause at a LOWER drawdown than the leg it challenges.
> - **`TTM_299_SS`** runs in paper from 2026-09-10 as the structural stop's forward test, with
>   `TTM_299_T` as its exact matched control. Its BOOK run against the book in production is queued;
>   the book figure does not change until that says so.

---

## What it is

Bollinger(20, 2.0) inside Keltner(20, 1.5 ATR) is Carter's "squeeze" — volatility coiled. The fire
is the bar the bands leave the channel; the side is the sign of the momentum oscillator; the entry
is the next open; the exit is the first bar momentum fades. Everything in this family is that, plus
**one filter that turned out to be the whole edge**: the trade is only taken while the *hourly*
squeeze is still on.

Engine: `augur_strategies/TTMSQZ_3_0.py` (family tag `TTM`). Fenced neighbourhood files around it:
`_ES30N` (run #299), `_ES30T` (run #340, the tilt), `_ES30SS` / `_ES30SS20` (the structural stop),
`_NQ15B`, `_R5NQ5`, `_R5ES15`, `_ES15N`.

## The one durable finding

**Higher-timeframe verification.** Round 4 gated every base cell on the 60-minute squeeze still
being compressed at the decision bar: net-positive in all twelve cells (NQ/ES × 5m/15m/30m × both
entry styles), drawdown cut three to six times. Directional higher-timeframe gates — sign, rising,
recently-fired — mostly fail. **The value is that the higher timeframe is still COILED, not that it
agrees about direction.**

That check then travelled outside the family: every crowned strategy's coiled-hour trades earn 2–3x
the expectancy of its others, which became the compression tilt now running on the NOISE and ENGU-Q
paper legs (see `KEEL.md` / memory `edgelog-keel-overlay`).

## Rounds 1–12

| Round | Question | Verdict | Where |
|---|---|---|---|
| 1 | Which timeframe? | Below 15m costs eat it; NQ 30m Keltner 2.0 best ungated | STUDIES `ttmsqz`, rows 251–344 |
| 2 | Different mechanisms (entry dir/fill, confirm, gates, exits) | Two pockets held; fade-the-fire and daily-squeeze gate dead | `ttmsqz2`, rows 346–595 |
| 3 | Daily bars, Carter's original habitat | Dead — the only big number is month-long bull holds | `ttmsqz3`, rows 442–465 |
| 4 | **Verify a short timeframe with a higher one** | **THE FINDING** — 12 of 12 cells net-positive | `ttmsqz4`, rows 596–1163 |
| 5 | The compression dial (gate_ratio, gate_len) | Overturned by its own validates — the strict gate IS the edge | `ttmsqz5`, rows 696–1164 |
| 6 | 24-hour tape; compression as a cross-family feature | Tape dead; the feature travels (became the KEEL tilt) | `ttmsqz6`, rows 1262–1337 |
| 7 | **TTM as a BOOK LEG**; daily ETFs | **The answer: a leg.** ETF tape dead | `ttmsqz7`, rows 1338–1366 |
| 8 | Twelve one-change variants of the crown | 0 of 12 clear the bar; near miss = the deep-squeeze size tilt | `ttmsqz8`, rows 1382–1394 |
| 9 | An ES-only TTM sub-book (15m, 5m cells) | No — the 30m cell is the only uncorrelated one | `ttmsqz9`, rows 1430–1444 |
| 10 | How many contracts? | Crowned nothing — and found the book drawdown clause is inert here | `ttmsqz10`, rows 1457–1468 |
| 11 | Can the tilted leg be traded in whole contracts? Cost stress | 3→4 keeps 98.5% of it; leg survives 3x house cost | `ttmsqz11`, rows 1470–1484 |
| 12 | Five parallel hunts for a new version of the squeeze | Four dead, one lead (the structural stop), one look-ahead bug caught | `ttmsqz12`, rows 1584–1599 |

## Validated runs

| Run | File | Verdict | Whole run | Lockbox | Note |
|---|---|---|---|---|---|
| #299 | `TTMSQZ_3_0_ES30N.py` | **PASS** | 359 trades · $51,709 · PF 2.12 · DD $3,740 | $4,992 · PF 2.22 · 16 trades | The crown cell |
| #340 | `TTMSQZ_3_0_ES30T.py` | **PASS + bar cleared** | 359 · $69,884 · PF 2.23 · DD $4,549 | $6,948 · PF 2.38 | The tilt. Search re-crowned #299's exact cell, so #299 is an exact control |
| #341 | BOOK, tilted leg | — | $1,174,222 · DD $34,329 | $199,035 | +4.9% money at identical drawdown; **missed the +5% MAR clause by 0.15%** — owner overrode knowingly |
| #342 | BOOK, tilt + ES 15m cell | — | $1,241,601 · DD $34,564 | $209,287 | Cleared all three clauses — but see #343 |
| #343 | `TTMSQZ_3_0_ES15N.py` | **WEAK** | 879 · $52,163 · PF 1.39 | $5,472 · PF 1.36 | Luck check fails; crowned a different cell than #342 ran, so **#342 does not transfer** |
| #352 | `TTMSQZ_3_0_ES30SS.py` | **PASS, bar missed** | 665 · $109,651 · PF 2.00 · DD $7,143 | $22,404 · PF 2.94 · 40 trades | Search walked to gate length 16; drawdown 57% over the cap for a dead-heat MAR |
| #353 | `TTMSQZ_3_0_ES30SS20.py` | **PASS + every clause cleared** | 357 · $101,017 · PF 2.91 · DD $4,338 · MAR 1.450 | $16,977 · PF 6.72 · DD $2,003 | The structural stop with the verification length pinned at 20. Lower drawdown than the leg it challenges, in the whole run and the lockbox |

## Open leads

1. **The structural stop — VALIDATED (run #353), book run pending.** Stop at the far side of the
   squeeze range instead of 1.5 ATR. With the validated tilt: **$101,017 at PF 2.91, annualised MAR
   1.450 against the book leg's 0.957, drawdown $4,338 against $4,549 — lower — and a lockbox of
   $16,977 at PF 6.72 against $6,948 at 2.38, at a lockbox drawdown of $2,003 against $4,053.**
   Buffers of 0, 0.5 and 1.0 points behave alike, which is what a structural effect looks like.
   *Run #352 is the cautionary half:* the same file with the verification length free passed every
   gate and MISSED the bar, because the search walked to length 16 — 665 trades, drawdown $7,143
   against a $5,004 cap, for a dead-heat MAR. `_ES30SS20.py` pins that knob at the incumbent's own
   value; that is one change at a time, not a cell picked to fit a bar.
   *Gap stress (`tools/ttmsqz_r13_gap_stress.py`) corrected the obvious worry rather than confirming
   it:* the ATR legs stop on 10.6% of trades but carry **43–44% of gross losses** there, while the
   structural leg stops on 13.2% and carries **6.8%** — its five worst trades are all fade or
   session-close exits and its worst stop exit is $496. It survives 0–10 points of slippage on every
   stop fill and stop losses scaled 1–6x, still beating the book leg. **Overnight gap risk is zero:
   the leg is flat at every session close**, so the largest gap on the tape ($10,838, the 2024-08-05
   yen-carry unwind) reached no position. *Limits:* the stress aimed at the stop channel, which is
   not where this leg loses, and the one wide-stop-specific number (worst draw $2,952 vs $2,719) is
   a single trade.
2. **Contract schedule for live trading.** The tilt asks for 4.5 ES contracts at book weight 3, and
   there is no half contract. **3→4 keeps 98.5% of the ideal at less size** (recommended); 3→5 lands
   1.5% above it; 30→45 MES micros express the exact 1.5x to within 1%. **Never 2→3** — a smaller
   base gives up more than an exact tilt adds.

## Closed — do not re-propose

Daily bars (rounds 3 and 7b, futures and ETFs). The 24-hour tape. Free discovery on this family
(overfits 5 of 5). Squeeze Pro's three-level grading — the tightest level is too rare, 3 of 359
trades. Cross-instrument compression — ES and NQ hourly ratios correlate 0.82, and the neighbour
adds nothing (question closed). Coil shape — length, depth, slope, range-in-ATR, prior move: nothing
survives a holdout. Pullback entries (43–72% of fires never fill). Fixed time exits. Scaling out at
1R (risk-adjusted, not richer — same as ORB). An ES-only sub-book. The ES 15-minute cell as a leg.

## Discipline this family taught the shop

- **The pin tax.** A pinned file declares 14 knobs and searches none, so trades-per-knob fails on
  arithmetic and every multi-config surface comes back empty. Use a small fenced neighbourhood
  instead: four knobs, mechanism frozen in the wrapper.
- **A neighbourhood is only binding if the FILE enforces it.** Auto-Validate widens declared ranges
  when the optimum sits near an edge; run #290 crowned values outside its own fence and lost $51,596
  in the lockbox. Every file here refuses out-of-set configurations, returning `None` — never
  clamping, because clamping runs one thing and reports another.
- **Fix the size, or the search crowns the biggest.** Run #331 (NOISE) and run #352 (this family)
  both walked to the loosest corner of their fence. The multiplier and threshold of the tilt are
  fixed a priori for exactly this reason.
- **A scan result becomes a strategy FILE before it becomes a belief.** Round 12e reported a
  pre-session rule that beat the incumbent everywhere at p = 0.0000 and was reading the close of the
  day being traded. The file caught it by disagreeing with the scan. Memory:
  `edgelog-scan-then-strategy-file`.
- **A book result cannot certify a leg.** BOOK #342 cleared every clause with an uncertified leg in
  it; that leg then failed its own validate, and #342 did not transfer.
- **The whole-run drawdown clause can be inert.** This book's worst stretch is one month of tape the
  TTM leg never traded, so the clause could not bind at any weight. Judge book additions on the
  LOCKBOX drawdown. Memory: `edgelog-book-dd-clause-2020`.

## Running the harnesses

```
python tools/ttmsqz_round8_crown.py        # the crown vs one-change variants, alone and stacked
python tools/ttmsqz_round9_subbook.py      # ES-only sub-book, with the correlation matrix
python tools/ttmsqz_round10_weights.py     # sizing sweep + the drawdown-attribution diagnostic
python tools/ttmsqz_round11_execution.py   # whole-contract schedules and cost stress
python tools/ttmsqz_r12{a,b,c,d,e}_*.py    # round 12's five hunts
```

Every driver pins the window 2010-06-07..2026-06-30 with the lockbox from 2025-07-01, prices ES at
0.363 points a round trip and $50 a point, and writes a log of the same name under `tools/data/`.
The baseline book is cached in `tools/data/ttmsqz_round8_base.npz` — delete it to rebuild.

Board: COMPARE ▸ STUDIES, study keys `ttmsqz` through `ttmsqz12`. Bookmark: **B28**.
Memory: `edgelog-ttm-squeeze-study`.
