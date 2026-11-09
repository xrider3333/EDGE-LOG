# PREREG — ENGU-Q CANDLE STRENGTH + VOLUME, DAILY-TREND ALIGNED · ES 15m

**Owner order 11-09 (MANAGER #150, board w119).** Read candle strength (body/range, close location in
the bar, follow-through) plus volume (relative volume versus the same time-of-day average, volume on
the signal bar), trade only in the direction of the daily trend, enter and manage on a smaller
timeframe. **My slot is ES 15m.** Hold-to-close is required as a control; a random-entry control is
required; the dead catalogue must be checked; the power-first gate runs on gross versus cost
pre-walk-forward; **no 900-trial job before an owner GO.**

Design date 2026-11-09. Lane ENGUQ. Family **ENGU-Q**. Instrument **ES**, timeframe **15m**, session
**RTH**, master `ADJ_ES_15m_RTH.csv` (108,097 bars, 2010-06-07 .. 2026-11-06 — the registered
roll-corrected master). Stretch **pre-lockbox 2010-06-07 .. 2025-06-30**. **The lockbox is not
opened by anything in this document.**

---

## 1. THE DEAD CATALOGUE ALREADY CONTAINS THIS IDEA — read this before anything else

I checked the 289-entry tested catalogue and this week's scopes first, as ordered. **The brief is
close to an entry that is already dead, on this instrument, and it is not a near miss:**

| catalogue entry | instruments | verdict |
|---|---|---|
| **"Point-score leads (largest body + volume since low, trend filters)" as CBU-Q PTS rules** | **NQ, ES 1m** | **DEAD 0 of 40** |
| CBU rules v1 (close at new high of day, 200 EMA, volume), validate #481 | NQ, ES 1m | **FAIL — lockbox ROC −40.1** |
| Volume-ignition momentum (volume as the signal) | NQ | DEAD — best MAR 3.3; the 1m version died again in round 38 |
| VOLBAR relative-volume bars | NQ | DEAD |
| ORB size by breakout-bar relative volume | NQ | DEAD — **volume dead as a gate AND as a tilt**; thirds inverted |
| ORB touch entry gated on the breakout bar's finished volume | NQ | **VOID — look-ahead, ~91% of the "edge"** |
| Round 38 scalps part C incl. volume ignition | NQ 1m | DEAD 0 of 20 |
| Relative-volume bars / RVOL size tilt (scope `NEW_STRATEGY_HUNT_R3_2026-11-06.md`) | — | DEAD |
| prior-day candle as direction (same scope) | — | DEAD |

**"Largest body + volume + trend filter, intraday, on ES" is the owner's brief, and it returned
0 of 40.** I am not going to run a seventh variant of a dead mechanism and present a fresh coat of
paint as a new question. So this prereg does one of two things: it names what is genuinely untested,
or it closes at draft. It names two things.

## 2. What is actually new here, and the second one is the whole round

**(a) ES 15m.** Every catalogue entry for this mechanism is 1m or 5m. **At 15m, R is several times
larger, so cost as a fraction of R collapses** — and that lever is proven to work mechanically: BBRF
(ledger 2.220, yesterday's round) cut cost from 0.11-0.36 of 1R to 0.028-0.055 of 1R simply by
flooring the stop, and a 15m ATR stop is wider again. Several of the dead entries above are
explicitly cost-shaped ("fixed cells flat gross", "at zero cost best gross ..."), so the timeframe is
not a cosmetic change.

**(b) THE RANDOM-ENTRY CONTROL, which is the decisive instrument and the reason to run at all.**

**"Trade only in the direction of the daily trend" on a long index future is beta.** A long entry in
a daily uptrend makes money because the index drifts upward, not because the candle was strong and
the volume was high. **Every dead entry above measured signal and drift mixed together, and none of
them, as far as the catalogue records, was matched against a random entry in the same regime.**

**So the headline statistic of this round is NOT profitability. It is the paired difference between
the signal arm and a random-entry arm matched on regime and time of day.** If that difference is
below its own minimum detectable edge, **the strategy is beta with extra steps**, and that is the
result — a cleaner close than another "DEAD, best MAR 3.3", because it says *why* the whole class
keeps dying.

**My prior: under 15% that the signal arm beats its random control by more than the MDE.** Lower than
the 20% I gave BBRF, because the catalogue evidence here is more direct.

## 3. Look-ahead discipline — named explicitly, because this exact mechanism has been voided for it

The ORB volume filter was **void for look-ahead and it was 91% of the apparent edge.** That is the
single most likely way this round produces a fake number, so every guard is pinned here:

1. **The signal bar is COMPLETE before it is read, and the fill is the NEXT bar's open at market.**
   The ORB void came from using a breakout bar's *finished* volume while entering *inside* that bar.
   With a next-bar-open fill the bar's volume is legitimately known at decision time.
2. **Relative volume uses the same 15-minute time-of-day slot over the PRIOR 20 sessions only**, a
   rolling mean shifted by one session. Today's own volume never enters its own benchmark.
3. **The daily trend is read from the PREVIOUS COMPLETED session**, never from the forming one.
4. **Daily bars are resampled from the SAME 15m master.** There is no ES 1d master in
   `augur_uploads`, and I will not introduce a second source to manufacture one — a splice between
   two tapes is how this house has broken parity before. One tape, no translation.
5. **ATR and the moving averages are shifted one bar** before use.

## 4. The design

**Direction: LONG ONLY for r1.** The brief says "only in the direction of the daily trend"; the
symmetric short-in-a-downtrend arm doubles every cell, so it is **pre-declared as its own arm** and
not bolted on later.

**Daily trend filter:** the previous session's close is above the `N`-session simple moving average of
daily closes. `N` ∈ {20, 50}.

**Candle strength on the signal bar:**
- body / range ≥ `bf`, `bf` ∈ {0.5, 0.7}
- close location in the bar, (close − low) / range ≥ `cl`, `cl` ∈ {0.7, 0.9}
- **follow-through: the close is above the previous bar's high.** Fixed ON, not a knob — it is part of
  the brief's own definition of the shape, and holding it fixed keeps the grid small enough to read.

**Volume:** relative volume on the signal bar ≥ `rv`, `rv` ∈ {1.0, 1.5, 2.0}, measured as in §3.2.

**Stop:** `entry − max(s * ATR20, FLOOR_PT)`, `s` = 1.5, `FLOOR_PT` ∈ {10, 20} ES points. The BBRF
lever, carried because it is the one thing that round proved.

**Exit arms — three, and the first is the control MANAGER required:**
- **A · HOLD TO CLOSE** (out at the 15:45 bar's close, or the stop). The control.
- **B · fixed target** `entry + T * R`, `T` ∈ {1, 2, 3}, stop wins ties.
- **C · time stop** `M` bars held, `M` ∈ {4, 8, 16} (one, two and four hours of 15m bars), the session
  close overriding.

**I predict arm A beats B and C**, on seven independent reads in this lane (shelf No. 39's 0 of 15,
hold cap r2's 116 dead values, executor r1's 112%, Webull arm C's 26.09 → 6.17, pullback-break r2,
the R-exit retrofit's 0 of 5, and BBRF's monotone gradient). Writing that down now so the prediction
is testable rather than retrofitted.

## 5. The grid

| knob | values |
|---|---|
| `N` daily SMA | 20, 50 |
| `bf` body / range | 0.5, 0.7 |
| `cl` close location | 0.7, 0.9 |
| `rv` relative volume | 1.0, 1.5, 2.0 |
| `FLOOR_PT` | 10, 20 |

**48 entry cells.** The gate screens these at **arm A only**, because arm A is the control and the
question is whether the entry does anything at all. `T` and `M` go to the validate — after a GO.
**Gross is compared in R, never in points**, since R varies by cell.

## 6. The power-first gate, with the random control as the headline

For each entry cell:

- **n, sd and MDE** = `sd * sqrt(7.85 / n)` for the signal arm's per-trade R.
- **The random-entry control:** for every signal, draw a bar from the **same 15-minute time-of-day
  slot, on a different session that passed the SAME daily-trend filter**, and run the **identical**
  stop and arm-A exit. **20 draws per signal, seed fixed at 20261109** so the control is reproducible.
  Matching on slot and regime is what makes the comparison about the candle and the volume rather
  than about time of day or about being long in an uptrend.
- **The paired difference** `delta = mean(signal R) - mean(control R)`, with the MDE of that difference
  computed two-sample (`n = 15.7 * sd^2 / delta^2`, so `delta_min = sd * sqrt(15.7 / n)`).

**Gate verdicts, pre-declared:**

- **BETA, NOT A SIGNAL** — `delta` at or below the two-sample MDE. The cell is closed; its profits, if
  any, are the daily trend and not the candle. **If all 48 land here, the round closes at draft and
  that is reported as the result.**
- **THIN** — under 50 trades a year.
- **OPEN** — `delta` exceeds the MDE **and** the signal arm's mean R exceeds cost in R. Only these go
  to a validate, after a GO.

**No clause in this gate can be satisfied by construction.** That is a direct lesson from BBRF, where
my own ceiling clause turned out near-vacuous because a wide stop almost guarantees a large
favourable excursion; its 36 "OPEN" verdicts were worthless and I said so in `2.220`. A paired
difference against a matched control cannot fail that way: a strategy with no edge scores zero.

## 7. The bar — what counts as a pass

1. **`delta` beats its own MDE** (section 6) — the new clause, and the one I expect to fail.
2. **≥ 7 of 8 folds positive.**
3. **No single fold holds more than 40% of the net.**
4. **`one_episode` false** — worst drawdown no more than 1.3 × DD5.
5. **ROC@$30k positive, its lead counted across folds, not asserted.**
6. **≥ 50 trades a year**, no merging of cells to reach it.
7. **Positive net at both cost rows** (section 8).

**Four numbers on every reported stretch** — ROC@$30k, DD5, DD% from the equity high, Sortino — from
`augur_engine.drawdowns.four_numbers`, **Sortino daily including zero days, never per trade**. **A run
record per reported cell**, from its own daily dollar series.

## 8. Cost

| rung | what it is |
|---|---|
| **0.45 ES pt** | the real house round trip, $5.66 both sides, MANAGER #144 |
| **0.95 ES pt** | the same with the $5-a-side slippage a market order pays on both legs |

The 0.533 house headline is carried in the JSON for comparability. **My old 0.08 and 0.10 rungs are
not used** — they are below any real cost and the claim they supported is withdrawn in ledger 2.218.

## 9. What this round will NOT do

- **No lockbox opened**; pre-lockbox only, ending 2025-06-30.
- **No trial budget and no strategy file before an owner GO** (MANAGER #150).
- **No short arm**, no limit fills ("through the level by one tick" remains unimplemented in this lane
  and stays its own pre-declared arm), and **no second data source** for the daily trend.
- **Nothing touches live, paper, the box or any account.**
- **No bound re-cut after seeing a result.** A method change is an addendum with its own sha, as in
  `2.218` and `2.220`.
