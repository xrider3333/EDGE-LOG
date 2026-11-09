# PREREG — ENGU-Q BODY BREAK, R-FLOORED (BBRF) · ES 5m · intraday only

**Owner order 11-09 (MANAGER #149):** build a NEW strategy designed around a fixed R/R target or any
exit that leaves before end of day — not a bolt-on to an existing crown, because the R-exit retrofit
is dead (0 of 5 on every crown). Board row w118. This document is the design, frozen before any
measurement. **Nothing is queued and no trial budget is spent until MANAGER gives a GO.**

Design date 2026-11-09. Lane ENGUQ. Family **ENGU-Q**. Instrument **ES**, timeframe **5m**, session
RTH, master `ADJ_ES_5m_ETH.csv`. Stretch pre-lockbox **2010-06-06 .. 2025-06-30** (the cut r2 used).
**The lockbox is not opened by anything in this document.**

---

## 1. My prior, stated first and against the round

**I expect this to fail, and the order is still worth running.** Six independent reads in this lane
say shortening this family's hold taxes the edge:

| # | read | what it found |
|---|---|---|
| 1 | shelf No. 39 holding rule | 0 of 15 holding rules helped; the ceiling IS the leg |
| 2 | hold cap r2 | 116 cap values, all dead |
| 3 | executor r1, T08 | 112% of its net came from holds through the close |
| 4 | Webull arm C | ROC 26.09 → 6.17 when the hold was shortened |
| 5 | pullback-break r2 (11-06) | the 1R flat-at-close exit lost to a multi-day hold on **every** statistic |
| 6 | R-exits r1 (11-09) | 1/2/3/4R on every crown, **0 of 5 each** |

**So why run it at all, rather than closing at draft?** Because read 5 — my own — identified the
*mechanism* of the failure, and it was not the exit. **Measured risk in r2 was 1.5 to 5.3 ES points,
so the real house round trip of 0.45 pt was 8% to 30% of 1R.** A trade that small cannot carry a
futures round trip no matter what you do at the exit. That is an arithmetic problem, not a market
finding, and it is fixable by construction. **This design is the same family's one supported entry
shape with R deliberately floored large enough to carry cost.** If it still fails, read 5 graduates
from "the exit was wrong" to "the entry has no intraday edge", which is worth knowing.

**Honest probability it clears the bar in section 5: under 20%.** I am not going to pretend a
seventh look at a question answered six times is likely to turn over.

## 2. What the entry is, and why this entry and no other

**The only part of this family's intraday shape with independent support is the big breakout body.**
Two separate reads say so, and both were against my own stated prior:

- **pullback-break r2:** gross R is negative in essentially every no-body-test cell and positive in
  most body≥2x cells; **every positive-net cell on the 106-row grid was a body≥2x cell.**
- **crown overlap r1:** the body≥2x slope arms carry lifts of **4.15 to 4.57** against crown #335's
  own entries, the highest anywhere, while the strict-drift arms sit at 1.21 or below. My prereg had
  predicted the body test would "add little"; it was wrong, and this design is built on what was
  right instead of on what I guessed.

**Entry conditions, all required, evaluated on the SIGNAL bar and FILLED AT THE NEXT BAR'S OPEN at
market** (the r2 fill bug was precisely a failure to honour this pin, so it is restated here and
guarded in the harness selftest):

1. **A measured decline over `w` bars:** the least-squares slope of the close over the trailing `w`
   bars is at most `-(d * ATR20) / w`. This is r2's `D2'` arm, the one with the lift.
2. **The break bar:** close above the previous close **and** above its own open.
3. **The body test:** the break bar's body is at least `b` times the mean body of the prior `w` bars.
4. **Regime:** the session is green so far and price is above the 200-bar simple moving average,
   both read with a one-bar shift. Carried unchanged from r2.
5. **RTH only**, and **no entry after 14:30 ET**, so a time stop has room to resolve inside the
   session rather than being overwritten by the close.

## 3. What is NEW here — the R floor, which is the whole point

**Stop:** `entry - max(s * ATR20, FLOOR_PT)` points.

**This is the design change and the reason the round is not a repeat.** Flooring the stop does three
things at once, and the second is the one that matters:

- it widens R, so **cost falls from 8-30% of 1R to roughly 3-6%** at the real 0.45 pt round trip;
- it makes the fixed-R target the owner asked for **arithmetically reachable** — a 1R target on a 2 pt
  stop is asking the tape to pay a 0.45 pt toll on a 2 pt move, which is why r2's X1 arm could not win;
- it cuts the trade count, which costs power, and that trade-off is measured in section 6 rather than
  assumed away.

**Target:** `entry + T * R`, a fixed R multiple — the owner's fixed R/R. **Stop wins ties**: when a
bar's range covers both the stop and the target, the stop is taken. Conservative by construction, and
unfalsifiable optimism at the tie is how an intrabar result gets invented.

**Time stop — the owner's "exits before the close", honoured exactly.** Flat at the **earlier** of:
(a) `M` 5-minute bars held, (b) the **15:55 ET bar's close**. **Every trade is closed the same
session. There is no overnight hold anywhere in this design**, which is the respect in which it is
not the multi-day exit that beat it in r2.

## 4. The grid, with hard bounds, and what the gate screens versus what the validate searches

| knob | values | why bounded here |
|---|---|---|
| `w` slope window | 15, 20 | r2's lift lived at w=15 and w=20; w=10 was weaker on both reads |
| `d` decline, × ATR20 | 0.5, 1.0 | d=1.5 thinned the count without raising the lift |
| `b` body multiple | 2.0, 3.0 | 2.0 is the supported value; 3.0 asks whether more is better |
| `s` ATR stop multiple | 1.5, 2.5 | |
| `FLOOR_PT` R floor, ES points | 8, 12, 16 | 12 pt puts the real round trip at 3.75% of 1R |
| `T` target, × R | 1.0, 1.5, 2.0, 3.0 | the owner's 1/2/3/4R, re-cut to the R range this stop produces |
| `M` time stop, 5m bars | 12, 24, 48 | one, two and four hours |

- **The power-first gate screens the ENTRY and the R FLOOR only** — 2 × 2 × 2 × 2 × 3 = **48 cells** —
  on gross versus cost in **R**, never in points. Whether the entry has an edge net of cost at a given
  R does not depend on where the target sits, and screening 576 cells would be a selection-bias
  machine dressed as a scan.
- **`T` and `M` are searched by the validate**, inside the bounds above, on the 900-trial budget
  (never lowered, owner rule) — and only after a GO.
- **Gross is compared in R, not in points.** When R is a variable quantity, a points comparison across
  cells compares position sizes rather than edges. This was my charge against MANAGER's scan r1 and
  then a mistake I made myself in r2; it is pinned here so it cannot happen a third time.

## 5. The bar — what counts as a pass, declared before the numbers

A pass needs **all** of:

1. **≥ 7 of 8 folds positive** (p 0.035, the discovery bar for a new seed). 6 of 8 is suggestive only
   and does not pass.
2. **No single fold holds more than 40% of the net.** This clause disqualified Webull arm A at 35%
   and r2's grid leader at 92.3%, and it is the clause most likely to kill this one too.
3. **`one_episode` false** — worst drawdown no more than 1.3 × DD5.
4. **ROC@30k positive and its lead holding across folds**, counted, not asserted.
5. **≥ 50 trades a year**, with no merging of cells to reach it.
6. **Positive net at BOTH declared cost rows** (section 7).

**The four numbers on every reported stretch** — ROC@$30k, DD5, DD% from the equity high, Sortino —
from `augur_engine.drawdowns.four_numbers`, **Sortino daily including zero days, never per trade**.
**A run record per reported cell**, written from each cell's own daily dollar series.

## 6. The power-first gate, and the arithmetic that decides whether this round opens at all

**The gate runs before any trial budget is spent and can close the round at draft.** Per-group n for
a one-sample mean at 80% power, two-sided 5%, is `n = 7.85 * sd^2 / delta^2`, so the minimum
detectable edge at a measured n is `delta = sd * sqrt(7.85 / n)`.

- Per-trade R has an sd near 1.0 for a stopped system, so at 3,000 trades the MDE is about
  **0.051 R**, and at 1,000 trades about **0.089 R**.
- Real cost at a 12 pt floor is **0.0375 R**. So the round is **powered**: the edge needed to be
  visible is of the same order as the toll, which is exactly what was NOT true in r2, where cost alone
  was 0.11-0.36 R and no achievable edge could show through it.
- **The gate's rule: if the measured gross R per trade is below the MDE at the measured n, the cell is
  closed at draft and not sent to a validate.** If every one of the 48 cells is, the round closes
  before it spends a trial, and I will report that as the result rather than as a non-event.
- **The R floor is also measured against itself:** a bigger floor cuts the trade count and so raises
  the MDE. The gate reports n, sd, MDE, gross R and cost R per cell so the trade-off is visible
  instead of argued.

## 7. Cost — two rows, both named, neither invented

| rung | what it is |
|---|---|
| **0.45 ES pt** | the real house round trip, $5.66 both sides at the same broker as NQ, at $12.50/pt — MANAGER #144 |
| **0.533 ES pt** | the house headline, carried for comparability with r2 and the ledger |
| *0.95 ES pt* | the real figure **with** the $5-a-side slippage, reported beside the others because **every fill in this design is a market order** and a fixed-R intraday system pays that toll on both legs |

**My 0.08 and 0.10 ES rungs from r2 are not used.** MANAGER #144 established they are below any cost
that exists, and the claim they supported is withdrawn in ledger 2.218.

## 8. The strategy file, if and only if the gate passes

A plain strategy file, no `exec` and no `compile`, stamped `# AUGUR-SOURCE: claude-review`, with
**ranged** `DEFAULT_PARAMS` whose min/max are the hard bounds in section 4 — not a pinned card, so the
Auto-Validate searches a real space and section 2 of the report exists. It goes through the plugin
gate (`REVIEWED.json` stamp plus whitelist) before the engine imports it, then
`tools/gauntlet_queue.py --dry` before the real queue.

## 9. What this round will NOT do

- **No lockbox is opened.** Pre-lockbox only, ending 2025-06-30.
- **No limit fills.** Every entry and exit is a market order at a bar's open or at a touched level.
  The "count a fill only when price trades THROUGH the level by one tick" rule is still not
  implemented anywhere in this lane and stays a separate pre-declared arm.
- **Nothing touches live, paper, the box or any account.**
- **No trial budget before a GO**, per MANAGER #149.
- **No merging of cells** to reach the trades-a-year floor, and no re-cutting of the grid after seeing
  the gate — if a bound turns out wrong, it is recorded as an addendum with its own sha, the way the
  r2 drift definition was.

---

## ADDENDUM 1 — how the gate measures an entry's edge WITHOUT choosing a target

**Written before the gate ran, and appended rather than edited into section 6, so the frozen body
sha 6fe6f7525bfb84d66b9a7f7167ed8db68f79b5ab2182490c89d5b5e5d5ceeeea still stands for what was
declared first.**

Section 6 says the gate screens the entry and the R floor "on gross versus cost in R" and leaves `T`
and `M` to the validate. Writing the harness exposed that **"gross R per trade" is not defined until
something closes the trade**, so the gate needs a target-free statistic. It gets two, and they answer
different questions:

1. **The no-target baseline.** Hold to the **session-end reference exit** — out at the 15:55 bar's
   close, or at the stop if it is touched first. No target, no `M`. This is the entry's intraday
   expectancy in R with the floored stop and nothing else, and it is the honest headline.
2. **The ceiling any target could capture.** The mean **maximum favourable excursion in R** reached
   inside the session before the stop. No target can realise more than this.

**Why both, and the reasoning I will not fudge.** A negative baseline does **not** by itself prove no
`T` works: a target truncates the outcome distribution, and where the favourable excursion
mean-reverts, truncating it can raise expectancy above the hold-to-close figure. So a negative
baseline alone is not a close. **The MFE ceiling is what makes a close possible:** if the mean MFE in
R is below cost in R, then no target can clear cost, because a target cannot capture more than the
move that happened. That is the clause that can shut the round.

**The gate's rules, pre-declared:**

- **HARD CLOSE for a cell** when its mean MFE in R is at or below cost in R. No target saves it, and
  it is not sent to a validate.
- **Powered-but-dead** when the baseline is negative and the MFE ceiling clears cost but the gap
  between them is below the cell's own MDE (`sd * sqrt(7.85 / n)`): the round would be asking a
  target to harvest an edge too small for this many trades to show.
- **OPEN** only when the MFE ceiling clears cost by more than the MDE. Those cells, and only those,
  are what a 900-trial validate would search `T` and `M` over — after a GO.
- **If every one of the 48 cells hard-closes, the round closes at draft** and that is reported as the
  result, not as a non-event.

Cost in R is computed per cell from its own measured mean risk, at **0.45 ES pt** (the real house
round trip) and at **0.95 pt** (with slippage, which a market-order system on both legs really pays);
the 0.533 house headline is carried beside them for comparability.

---

## ADDENDUM 2 — my CEILING clause was near-vacuous, and what replaces it

**Written after reading the 48-cell gate and before measuring anything else.**

**The clause failed as a discriminator, and that is a defect in my gate design, not a result.**
Addendum 1 made the hard close depend on the mean maximum favourable excursion in R falling at or
below cost in R. Measured, **the ceiling is 0.56 to 1.07 R in every one of the 48 cells** — including
cells whose held-to-close expectancy is plainly negative. **A floored, therefore wide, stop almost
guarantees a large favourable excursion somewhere in a session**, so the clause can never fire and
the 36 "OPEN" verdicts it produced are **not evidence of anything**. I am saying so before quoting
them anywhere as encouraging.

**The informative column is the baseline against its OWN MDE**, and on that column the gate is
decisive:

- **0 of 48 cells have a held-to-close expectancy distinguishable from zero.** Every cell's
  |baseline| is below its own MDE — the best positive is +0.0266 R against an MDE of 0.0768 R.
- **0 of 48 beat cost.** The best baseline anywhere, +0.0266 R, sits below that cell's own 0.0541 R
  real round trip.
- **The R floor DID do its job**, which is the one claim of this design that is confirmed: cost fell
  from r2's 0.11-0.36 R to **0.0275-0.0553 R**. The arithmetic problem is fixed and the edge still is
  not there, which separates the two questions cleanly.
- **More body is WORSE here:** the `b=3.0` cells are mostly negative while `b=2.0` is mostly
  positive-but-indistinguishable. The body test's value in r2 and in the overlap round does not
  extend to a third-multiple body, and I am not going to read it as if it did.

**The one door the baseline does not shut**, stated because it is true and not because I expect it to
open: a fixed target truncates the outcome distribution, so where the favourable excursion
mean-reverts, a target can pay more than holding to the close. **STAGE 2 tests exactly that, and it
does not need the trial budget** — the owner's `T` and `M` values are a small deterministic grid, not
a search.

**STAGE 2, pre-declared:**

- **Entry cells chosen by a RESULT-BLIND rule:** every entry cell with **n ≥ 2,000** trades, at
  `s = 1.5` only, across all three floors. That is 6 entry cells. The rule is trade count, which was
  fixed by the grid and cannot peek at an outcome; picking the cells with the best baseline would be
  selection on the thing being tested.
- **The owner's exits in full:** `T` ∈ {1.0, 1.5, 2.0, 3.0} × `M` ∈ {12, 24, 48} bars, with the
  15:55 flat overriding whichever comes first. 6 × 12 = **72 cells**.
- **Reported per cell:** the four numbers from each cell's own daily dollar series, the 8-fold count,
  the largest fold's share of net, `one_episode`, and net at **both** the 0.45 pt real round trip and
  the 0.95 pt figure with slippage.
- **The bar is section 5's, unchanged.** 7 of 8 folds, no fold over 40% of net, `one_episode` false,
  ≥ 50 trades a year, positive net at both cost rows.
- **A run record per reported cell**, written from its own daily series.
- **Still no trial budget and no strategy file before MANAGER's GO.**
