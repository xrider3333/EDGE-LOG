# ENGU-Q round 57 - pre-registration: change WHICH setups are taken

**Date:** 2026-09-14. **Written before any test file, test cell or test result exists.**
The research sibling named below does not exist yet (checked: `ENGUQ_1M_ETH_SEL_1_0.py` is free on
origin/main, in the shared checkout and in this worktree). Nothing in this document may be edited
after the first test cell runs, except to append a dated "deviations" section at the bottom that
says what changed and why.

**Owner ask (2026-09-14):** "run more test. try to improve the frontier ENGUQ model."

**Owner's framing (parked 2026-09-11, reopened today):** ENGU-Q was built to read the context of
the trade, its location, and the imbalance of buyers and sellers, so it should win often at a
modest profit factor. It wins 29.4% and is carried by a tail. The lever is the ENTRY RULE - which
setups are taken - not exits, stops, sizing or a model.

**Inputs this document relies on (all selection-window only):**
- Frontier table: `tools/r57_enguq_frontier.py`, `tools/r37_results/r57_frontier.txt` / `.json`.
- Signal-bar anatomy: `tools/r57_enguq_anatomy.py`, `tools/r37_results/r57_anatomy.txt`,
  per-trade table `C:\EdgeLog\_anatomy_cache\r57\r57_selection_signal_features.csv`.
- Imbalance probe: `tools/r57_imbalance_probe.py`, per-trade table
  `C:\EdgeLog\_anatomy_cache\r57\r57_imbalance_probe_features.csv`.
- Three hypothesis lenses (location, imbalance, context/timing) with trade-list reads in the
  round's scratchpad `...\scratchpad\r57\` (volatile; the numbers quoted below are the record).

---

## 0. What this round can and cannot show

- **It can show** whether one signal-time condition, written into a strategy file and run in the
  engine (so freed slots refill and re-timed signals are counted), improves the crown on the
  selection window by the house bars, survives a day-shift null, holds on its grid neighbours,
  replicates in sign at the tail-frontier settings, and survives a cost stress.
- **It cannot show** that the improvement will persist. Every hypothesis below was suggested by a
  screen of 160 features on the SAME selection trades (the anatomy), and the 2019-06..2025-06
  anatomy holdout was already peeked once in an earlier round. A pass here is "consistent
  in-sample, causally written, not a lone cell". The judges after this round are a fenced
  Auto-Validate (walk-forward folds) and a forward paper leg - both owner calls.
- **The lockbox (entries from 2025-06-30) is spent** for this family. It is read ONCE per surviving
  hypothesis, after every selection decision is final, as a confirmation only (section 8).
- **Prior expectation, stated before the run:** most or all of these will fail. The family's
  history is that entry filters built from trade anatomy lose money once written as rules
  (regime filter 0/5, battery V 6 of 7 gates dead, anatomy skip rules 0 robust, ML gates dead).
  The anatomy itself sets the ceiling: dropping the worst in-sample fifth of the strongest reads
  lifts win rate only to 30.4-31.1%, the best fifth anywhere wins 38.3% (family-wise p 0.037), and
  a logistic on all 160 features scores AUC 0.513 / 0.536 across periods. **Nothing here can make
  ENGU-Q "win often"; the question is whether an honest, modest improvement exists.**

---

## 1. Base config - ONE base for every test

**Base = the R2 file defaults = run #335 crown** (`augur_strategies/ENGUQ_1M_ETH_R2_1_0.py`
DEFAULT_PARAMS), traded by paper leg `ENGUQ_335` and by NinjaTrader since 2026-09-08:

```
tl_len 206 · ema_len 220 · atr_len 52 · buf_atr 0.3 · min_brk 1.6 · vol_mult 1.1
stop_mult 1.0 · act_R 1.5 · trail_frac 2.5 · breakeven_R 2.0 · limit_atr 0.55
regime_len 10 (390-bar blocks) · er_len 100 · er_th 0.0 · max_hold_bars 0
```

**Why this one:**
1. The owner trades it (paper + NinjaTrader). Ties go to the traded crown.
2. Every hypothesis below was measured on ITS trades at the true signal bar. Any other base would
   turn the evidence into a transfer.
3. The only config "ahead" of it on money is the R4 defaults (limit 0.85): PF 1.713 vs 1.717 is a
   tie, and R4's MAR lead (1.21 vs 0.90) comes from one lower max drawdown, which is an unreliable
   statistic on this family. That is a tie, so it goes to the crown.
4. The R5 defaults (limit 0.85 + cap 9,660) lead on tail independence but give up PF (1.519), their
   validate #381 is void and a fenced re-run is pending. R5 settings are used here as the
   REPLICATION setting (clause S11), because all four entry rules act on the same signal set and
   only fills and exits differ between R2 and R5.

**Control = the new sibling file with every new knob OFF, at R2 settings.** Its selection numbers
must equal the frontier table row 1 before anything is read (parity gate G1):

| stretch | n | win | PF | net | maxDD | MAR | EV R | top-10 E1 / E2 | ex-top-10 | trades-to-zero | index corr | 2018 / 2022 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| selection (entries < 2025-06-30) | 1,831 | 29.4% | 1.717 | $524,745 | $38,687 | 0.90 | 0.507 | 62.1% / 64.6% | $254,730 | 32 | +0.499 | $12,392 / $7,340 |
| LB (entries >= 2025-06-30, read in section 8 only) | 118 | 28.0% | 1.675 | $88,380 | $41,534 | - | - | - | - | - | - | - |

Whole window: 1,949 trades / $613,126. (ENGUQ.md's 1,830 / $522,613 was measured from 2010-06-21;
the pinned 2010-06-07 window adds exactly one warm-up trade. Proven in the frontier run.)

**Replication control (R5 settings, limit_atr 0.85, max_hold_bars 9,660, all else R2):** selection
2,434 trades / win 28.4% / PF 1.519 / $466,910 / DD $30,527; whole window 2,585 / $566,907.

---

## 2. Shared protocol (every cell)

- **Data:** NQ 1-minute ETH master `NOADJ_NQ_1m_ETH.csv` (source `db_noadj_eth`, registry id 34),
  window **2010-06-07 .. 2026-06-30 pinned** (the masters have a real hole 2026-07-01..08-05; never
  extend). Loaded with `augur_engine.data.load_master_arrays`, which also supplies `volume`,
  `day_id` and the ET `index`.
- **Engine call:** `augur_engine.engine.run_backtest(...)` with EVERY parameter passed explicitly
  (the `{}` trap), `cost_pts=0.533`, multiplier $20, `return_trades=True`. Engine-path tuples are
  already cost-netted. One continuous backtest per cell.
- **Split:** trades sliced by ENTRY time. Selection = entries before 2025-06-30 00:00 ET. LB trades
  are discarded the moment the engine returns and are not printed, until section 8.
- **Metrics:** computed by `measure()` in `tools/r57_enguq_frontier.py` (worktree), unchanged -
  the same harness that produced the frontier table. Section 3 restates what it computes.
- **Research sibling:** `augur_strategies/ENGUQ_1M_ETH_SEL_1_0.py`, written in this worktree, a
  copy of `ENGUQ_1M_ETH_R5_1_0.py` (which reproduces R2 exactly at limit 0.55 / cap 0) with
  DEFAULT_PARAMS reset to the R2 defaults above, `_AUGUR_PARENT = "ENGUQ_1M_ETH_R2_1_0.py"`, and
  four new knobs, all default OFF:
  `quiet_pct` (H-A), `stretch_max` (H-B), `rec_min` (H-C), `vol_clock` (H-D).
  The signature must declare `index=None` explicitly (the engine and `auto.py` pass timestamps,
  including walk-forward slices, only to plugins that name `index`). If any session-keyed knob is
  on and `index` is None, the file raises; it must never go silently inert.
- **One knob at a time.** Each hypothesis is tested with the other three knobs OFF. If one passes,
  a fenced single-hypothesis file is cut later for its validate; the research sibling is never
  validated as a four-knob search.
- **Compiled path preserved, `fastloop.py` untouched.** Every rule is a boolean per-bar mask that
  is ANDed into the existing `er_ok` argument of `fastloop.engu_walk` (or passed as `er_ok` when the
  efficiency gate is off). The compiled walk already tests `er_ok[i]` at the SIGNAL bar `i`, after
  the breakout tests and before the resting limit is placed, and a failed test moves the walk to
  `i+1` exactly like any other failed filter. The fill bar `j` (i+1..i+10) is never read by any
  rule. With a knob OFF the mask is `None` and the byte-identical compiled walk runs. The
  interpreted fallback applies the same mask beside its `er_ok` test. Knob-free arrays (the
  percentile reference, session aggregates, the clock-volume baseline) are memoised at module
  level keyed by (bar count, first and last timestamp, volume nbytes), so a later 900-trial
  validate pays them once per process.
- **Research-only instrumentation** (not part of the strategy contract, never in a validate):
  `_mask_override` (a boolean array that replaces the rule's computed mask, used by the null in
  S12; keeps the compiled path), and `_signal_index_probe` (a list the interpreted walk appends the
  signal bar index to; used only for audits).
- **Speed and hygiene (BACKTEST_SPEED.md):** drivers run with cwd = the shared checkout,
  `AUGUR_TRIAL_CACHE=1`, `OMP_NUM_THREADS=1`, multiprocessing under `if __name__ == "__main__":`,
  **at most 4 worker processes**. Any run over ~2 minutes is wrapped in `tools/research_beacon.py`
  if the executing session is allowed to write Firestore; if it is not, the driver prints progress
  and the write-up says the beacon was not used. Caches live under `C:\EdgeLog\_anatomy_cache\r57`.
  Result-bearing drivers are saved under `tools/` in the worktree (scratchpads get wiped).
- **No commits, pushes, queued jobs, runner restarts or Firestore writes** in this round.

---

## 3. Metric definitions (all on the selection stretch, P&L after cost)

- **win** = share of trades with net P&L > 0 (breakeven scratches count as losses).
- **PF** = gross $ won / gross $ lost. **net**, **maxDD** on the entry-ordered cumulative P&L.
- **MAR** = (net / selection years) / maxDD, selection years from the first entry to 2025-06-30.
- **EV R** = (1 - win) x (PF - 1). **Proportional-tail EV R** = the same after deleting the top
  0.5% of the stretch's own trades by $ (`evr_ex05` in `measure()`).
- **Eras for concentration:** E1 = entries 2010-06-07..2019-12-31, E2 = 2020-01-01..2025-06-29.
  **top-10 share** per era = (sum of that era's 10 best trades) / era net; **ex-top-10 net** = era
  net minus that sum. The whole-window share is printed but never quoted as the concentration.
- **Four eras for consistency:** A 2010-06-07..2013-12-31, B 2014..2017, C 2018..2021,
  D 2022-01-01..2025-06-29 (entry time). PF lift per era = variant PF - control PF in that era.
- **trades-to-zero** = number of best selection trades by $ deleted before net <= 0.
- **index corr** = correlation of selection net by entry year with NQ's calendar-year
  close-to-close return, 2011..2025 with 2025 truncated before 2025-06-30 (15 points; `corr_sel`).
- **top-20 retention** = how many of the control's 20 best selection trades by $ have a variant
  trade whose entry bar lies inside that control trade's [entry bar, exit bar] span.
- **Reported, never gating:** median winner / median loser vs break-even payoff, win rate
  excluding scratches (|net| <= 1 pt), R/YR, longest hold, whole-window numbers, slot-refill count
  (variant trades with no control trade in their span) and their win rate.

---

## 4. The shared selection pass bar

A hypothesis is judged ONLY at its **pre-declared centre cell**. Other cells never replace it -
there is no picking the best cell after the run. The centre must clear **every** clause below
against the matched knob-off control. The two grid neighbours of the centre are the plateau test
(S9). Hypothesis-specific clauses in section 5 are added to these, never substituted.

| # | clause (selection window, centre cell vs control) | R2 threshold |
|---|---|---|
| S1 | win rate >= control + 1.0 pt | >= 30.4% |
| S2 | PF >= control + 0.02 | >= 1.737 |
| S3 | net >= 95% of control | >= $498,508 |
| S4 | MAR >= control - 5% (guard only; maxDD is unreliable) | >= 0.86 |
| S5a | per-era top-10 share <= control + 2 pts | E1 <= 64.1%, E2 <= 66.6% |
| S5b | ex-top-10 net > 0 inside E1 AND inside E2 | > $0 each |
| S5c | trades-to-zero >= control - 2 | >= 30 |
| S5d | proportional-tail EV R >= control's (same harness, same run) | >= control `evr_ex05` |
| S6 | PF lift > 0 in >= 3 of eras A-D; PF lift > 0 in E2; win lift > 0 in E1 AND in E2 | - |
| S7 | index corr <= control + 0.05; 2018 and 2022 selection P&L each >= $0 | corr <= 0.549 |
| S8 | top-20 retention >= 17 of 20 (H-A: >= 18) | - |
| S9 | PLATEAU: BOTH neighbour cells: win lift >= +0.5 pt, PF >= control + 0.01, net >= 90% of control, E2 PF lift >= 0 | win >= 29.9%, PF >= 1.727, net >= $472,271 |
| S10 | COST STRESS at 0.783 pts/RT (variant and control both re-run): win lift >= +0.5 pt, PF lift > 0, net >= 95% of the 0.783 control | - |
| S11 | REPLICATION at R5 settings (limit 0.85, cap 9,660), centre cell vs the R5-settings knob-off control: win lift >= 0, PF lift >= 0, net >= 95% | net >= $443,565 |
| S12 | DAY-SHIFT NULL, 1,000 draws (below): p(win lift) <= 0.01 AND p(PF lift) <= 0.01 | - |

**S12 day-shift null (identical for every hypothesis).** Build a table from (session index,
ET clock minute) to bar index, sessions rolling at 18:00 ET (session key =
`(ET timestamp + 6 h).date`). For each draw pick an integer shift k uniformly from
[-250, -21] U [21, 250] sessions. The shifted mask at a selection bar in session s, minute m is the
real mask at (session s+k, minute m), with s+k wrapped circularly inside the selection-window
sessions; if that bar does not exist the bar passes (True). LB bars keep the real mask (they are
never scored). Run the continuous backtest with `_mask_override` = the shifted mask and score the
selection stretch. A draw "matches" on win if its win lift >= the real win lift, and on PF if its
PF lift >= the real PF lift. p = (1 + matches) / 1,001, computed separately for win and PF. The
shift keeps each rule's time-of-day and run-length shape and breaks only its alignment with the
trades, so a pure clock effect or a pure "remove ~X% of signals" effect cannot pass. Fixed seed
20260914 for the draw sequence.

**A0 look-ahead alarm (stop and audit before reading further).** If a centre cell shows win lift
> +3.0 pts, or PF lift > +0.30, or net > 110% of control, the run stops. Before any result is
believed: `tools/exec_feasibility_audit.py --config` on the cell, a re-check that the mask is
indexed at the signal bar (interpreted walk with `_signal_index_probe`), and a recomputation of the
feature from bars <= i only. An effect far larger than anything the family has produced is the
house look-ahead tell (NOISE r47, NOISE r51, TTM r12e).

**Scan-vs-file agreement (reported, never tuned toward).** The trade-list reads predicted, at the
centre cells: H-A win +1.1 pt / PF +0.05 / net +$14.9k; H-B win +1.0 / PF +0.15 / net -$17.6k;
H-C win +1.5 / PF +0.08 / net -$16.9k; H-D no prediction (it adds trades a scan cannot see). The
in-engine number is the result; a gap is explained (slot refill, re-timing) and printed, never
closed by changing the file.

---

## 5. The four primary hypotheses

### H-A QUIET-TAPE STAND-DOWN (context: the market's own activity at the signal)

**Mechanism.** The breakout test is scaled to ATR, so in a dead tape (mostly the Asia session) a
"1.6-ATR decisive break on a volume spike" is a few ticks on a few prints. Nobody follows through,
the resting limit fills on bid-ask bounce or a gap between thin bars, and the break says nothing
about buyers. The rule stops judging breakouts when there is no market to judge. It touches no
stop, size, exit or trend level.

**Evidence (selection, signal bar).** Anatomy `ta:ind_atr_pctile_bar`: within-year null win
q 0.007, gross R q 0.017, rank-biserial **E1 +0.11 and E2 +0.11** - the most era-stable read in
the screen; within-year quintile win 22.6 / 30.8 / 28.0 / 30.0 / 35.6%. Trade-list read on the
exact R2 signal bars: signals with percentile < 20 = 194 trades, win 19.6%, PF 0.49, -$14,924,
worse in 4 of 4 eras and 12 of 16 years; keeping the rest gives win 30.5%, PF 1.768, net $539,670,
per-era top-10 60.2% / 63.0%, and removes 0 of the 10 best $ trades. At R5 settings the same bucket
is 316 trades, PF 0.76, -$10,730. 79% of quiet trades are Asia-session, but inside Asia an active
tape is PF(R) 1.63 vs 0.69 quiet, so it is not a clock rule.

**Rule (at signal bar i, after every existing entry filter passes).**
- `TR[k]` = the file's own true range array; `ATR14[k]` = mean of `TR[k-13..k]` (NaN for k < 13).
- Session key as in S12 (18:00 ET roll), factorised in bar order: `sess[k]`.
- Reference for session s: the values `ATR14[x]` at bars `x = start_t, start_t+23, start_t+46, ...`
  (stride **frozen at 23**, about 60 samples per 1,380-bar session) for every session t in
  s-252..s-1 present in the frame; NaN dropped; requires s >= 60 and >= 100 samples; sorted.
- `q[k] = 100 * searchsorted(ref_s, ATR14[k], side="right") / len(ref_s)` for each bar k of session
  s; NaN when the requirements fail or `ATR14[k]` is NaN.
- **Drop the signal if `quiet_pct > 0` and `q[i]` is finite and `q[i] < quiet_pct`.** NaN passes.
- Information time: `ATR14[i]` uses bars <= i; the reference uses only completed earlier sessions.

**Grid:** `quiet_pct` in {0 = OFF, 10, **20 = centre**, 30}. Neighbours of 20: 10 and 30.
ATR length 14, lookback 252 sessions, 60-session minimum and stride 23 are frozen, not knobs.

**Feature parity gate (G4-A).** In-engine `q` must equal, to 1e-9, a local copy of
`tools/trade_anatomy.pctile_vs_prior_days(calc_atr(h, l, c, 14), sess, 252, 60, 60)` with its stride
forced to 23, built on the same continuous frame. Sanity only (the anatomy column was built in
3-year chunks with chunk-dependent stride, documented drift up to ~8% relative): against the
anatomy CSV `ta_ind_atr_pctile_bar` on the recovered signal bars, median |diff| <= 1.5 pts.

**Extra clauses.**
- S8 is tightened to >= 18 of the control's top-20 $ trades retained.
- Reported diagnostic, not a gate: a floor on planned risk as % of price at the signal
  (`(limit - swing_low) / limit`, limit = `c[i] - 0.55 x ATR52[i]`) set outcome-blind to remove the
  same share of control signals as the centre mask. If it matches H-A's win and PF lift, the
  write-up says H-A is the known big-stop / volatility factor expressed era-neutrally.
- Reported: share of removed signals by session bucket (Asia 18:00-03:00, Europe 03:00-09:30, cash
  09:30-16:00, other).

**Kill criteria (any one = dead this round).** Any S-clause fails at the centre; either neighbour
fails S9; in-engine win lift below +0.55 pt (half the scan's +1.1, meaning freed slots refill with
the next quiet-adjacent signal); removes any of the control's top-10 $ trades without an in-span
replacement; R5 replication moves the other way on win or PF.

---

### H-B DAILY STRETCH CAP (location on the daily chart)

**Mechanism.** A 1-minute trendline break is a short-horizon long. When price already sits more
than ~1.5 daily ATRs above its 20-session mean, the multi-day move has used its expected range;
the 1-minute pullback is more often the first leg of a daily mean reversion that runs through the
swing-low stop. The same break near or below the 20-session mean is a higher-timeframe pullback
resuming. The trend core stays (close above the 220-bar EMA and the 3.6-day regime mean); only
late-trend chasing is removed. Note it contradicts the owner's "above the larger moving averages"
beyond the local EMA: far above the ~20-day mean wins LESS.

**Evidence (selection, signal bar).** Anatomy `ta:lvl_sma20d_atr`: within-year null win q 0.020,
gross R q 0.009; rank-biserial E1 -0.13, E2 -0.03 (same sign, weak in E2 on win). Top global fifth
(>= 1.49) wins 25.2% with PF(R) 0.93, and PF(R) is 0.92 in E1 and 0.94 in E2 against era averages
of 1.21 / 1.56 - the per-R damage holds in both eras. Trade-list cut at < 1.49: kept 1,468 trades,
win 30.4%, PF 1.866, net $507.1k (96.6%), PF up in 4 of 4 eras. Independent of volatility (within
volatility terciles the win separation is -0.06 / -0.04 / -0.14) and of H-C (Spearman -0.02).
**Warning carried into the kill list:** in era D the cut lowers net ($272.9k -> $244.8k) and raises
that era's four-era top-10 share.

**Rule (at signal bar i).**
- Sessions as in S12 (18:00 ET roll). For each session t in the frame: `H_t` = max high, `L_t` =
  min low, `C_t` = close of its last bar.
- `TRd_t = max(H_t - L_t, |H_t - C_{t-1}|, |L_t - C_{t-1}|)` (first session in the frame: `H_t - L_t`).
- `ATRd_t` = mean of `TRd` over sessions t-13..t (NaN if fewer than 14); `SMA20_t` = mean of `C`
  over t-19..t (NaN if fewer than 20).
- For bar i in session s: `S[i] = (c[i] - SMA20_{s-1}) / ATRd_{s-1}`; NaN if either is NaN or
  `ATRd_{s-1} <= 0`. Only the last session fully closed before bar i's session began is used.
- **Drop the signal if `stretch_max > 0` and `S[i]` is finite and `S[i] > stretch_max`.** NaN passes
  (the first 20 sessions of any frame, including each walk-forward slice).

**Grid:** `stretch_max` in {0 = OFF, 2.0, **1.5 = centre**, 1.0}. Neighbours of 1.5: 2.0 and 1.0.

**Feature parity gate (G4-B).** In-engine `S[i]` must equal the anatomy CSV column
`ta_lvl_sma20d_atr` (trade_anatomy `build_day_features`: session SMA20 and ATR14, both shifted one
session, 18:00-roll `day_id` from `feature_board.load`) on every non-NaN selection signal bar
(1,828) to 1e-6.

**Extra clauses.**
- Era D selection net >= 90% of the control's era D net.
- Win lift > 0 in era C or era D (not a 2010-2019-only effect).

**Kill criteria.** Any S-clause fails at the centre; either neighbour fails S9; era D net falls
more than 10%; win lift <= 0 in both era C and era D; R5 replication reverses sign.

---

### H-C LEG RECOVERY FLOOR (location inside the structure)

**Mechanism.** The 206-bar descending trendline can break while price is still near the bottom of
its falling leg, usually after a steep V-shaped selloff. That break is the first bounce off a
capitulation low: the leg's supply is still overhead, the resting limit is more often filled by
price falling back through it (16% gap-through fills in the lowest-recovery fifth vs 4-8% in the
others) and the stop is that same swing low, so it is retested. A break that has already reclaimed
about half of the leg shows buyers absorbed sellers through the middle of the range - the owner's
"the pullback holds a level" base breakout, not a knife catch.

**Evidence (selection, signal bar).** Anatomy `loc_pb_recovery`: within-year null win q 0.045,
gross R q 0.044; rank-biserial E1 +0.10, E2 +0.04 (same sign, weaker in E2). Global lowest fifth
(< 0.478) wins 23.4%, PF(R) 0.96; E1 lowest fifth PF(R) 0.85, E2 lowest fifth 1.26 against an E2
average of 1.56. Trade-list cut at >= 0.478: kept 1,462 trades, win 30.9%, PF 1.80, net $507.8k
(96.8%), top-10 53.2%; PF up in 3 of 4 eras (2014-17 slips 1.426 -> 1.402). Same sign inside all
three within-year volatility terciles; Spearman with ATR%price +0.26. Not the same as breakout size
(`imb_brk_atr` has no win signal, p 0.16).

**Rule (at signal bar i).**
- `WH[i] = max(h[i-tl_len .. i-1])` (the trendline window's highest high; tl_len = 206).
- `SL[i] = min(l[i-tl_len .. i])` (exactly the file's `swing_low`, bar i included).
- `rec[i] = (c[i] - SL[i]) / (WH[i] - SL[i])` if `WH[i] > SL[i]`, else NaN.
- **Drop the signal if `rec_min > 0` and `rec[i]` is finite and `rec[i] < rec_min`.** NaN passes.
- Vectorised with rolling max/min (O(n)); known at bar i's close.

**Grid:** `rec_min` in {0 = OFF, 0.35, **0.45 = centre**, 0.55}. Neighbours of 0.45: 0.35 and 0.55.

**Feature parity gate (G4-C).** In-engine `rec[i]` must equal the anatomy CSV column
`loc_pb_recovery` on all 1,831 selection signal bars to 1e-9.

**Extra clauses.**
- Reported mechanism check: the gap-through fill share among selection trades must not rise.

**Kill criteria.** Any S-clause fails at the centre; either neighbour fails S9; in-engine win lift
below +0.75 pt (half the scan's +1.5); era D net falls more than 10%; R5 replication reverses
sign.

---

### H-D CLOCK-UNIT VOLUME TEST (imbalance: the owner's "genuine volume spike")

**Mechanism.** The file's volume test (volume >= 1.1 x the 20-bar mean including the bar) passes
almost automatically at every session transition (18:00, 03:00, 08:30, 09:30), because the prior
20 bars are the quiet minutes before it, and asks little in steady hours. Among taken signals it
has no link to outcome at all. Volume measured against the SAME CLOCK MINUTE over the prior 20
sessions is the OHLCV stand-in for "unusual participation for this time of day". As a REPLACEMENT
(not an extra filter) it removes routine transition bars and adds steady-hour breakouts whose
volume is high for their minute but below a burst-inflated 20-bar mean. One multiplier encodes the
owner's "3x when quiet, ~1.3x on busy opens", because the baseline already scales with the clock.

**Evidence (selection, signal bar) - weakest of the four, stated plainly.** The file's own test:
`imb_vol_ratio20` rank-biserial -0.010, within-year win p 0.94. Clock-relative volume
`imb_vol_vs_clock20`: within-year quintile win 25.8 / 28.4 / 29.8 / 31.1 / 31.8%, same sign in both
eras (Q5-Q1 +5.4 pts E1, +4.4 pts E2), but **not FDR-significant** (win q 0.21, gross R q 0.126).
Nearly independent of volatility (Spearman +0.09). Risk: as a pure AND filter at 1.0 it kept only
26 of the 36 best-R trades at 80% of signals, so the tail often starts on ordinary-for-the-clock
volume (hence S8 and the kill list). The added half of the rule is invisible to any trade-list scan.
It is included because it is the only clean, one-knob, compiled test of the owner's named
imbalance idea; its anatomy support is not a reason to expect a pass.

**Rule (at signal bar i).**
- Sessions as in S12; clock minute `m[k]` = ET hour x 60 + minute.
- `B[k]` = mean volume of the bars at minute `m[k]` in sessions `sess[k]-20 .. sess[k]-1` that
  printed that minute; NaN if `sess[k] < 21` or fewer than 10 such prints.
- **When `vol_clock > 0`:** the 20-bar test is switched OFF (the file passes `vol_mult = 0.0` to the
  walk, whose own test is `vol_mult > 0 and has_vol`), and the signal requires `B[i]` finite and
  `V[i] >= vol_clock x B[i]`. A NaN baseline FAILS (no trade in the first 21 sessions of a frame).
- `vol_clock = 0` = the R2 test at `vol_mult` 1.1 = parity.

**Grid:** `vol_clock` in {0 = OFF, 1.0, **1.25 = centre**, 1.5}. Neighbours of 1.25: 1.0 and 1.5.

**Feature parity gate (G4-D).** In-engine `V[i] / B[i]` must equal the anatomy CSV column
`imb_vol_vs_clock20` on every non-NaN selection signal bar (1,829) to 1e-9 (the probe already
matched it to 4e-15).

**Extra clauses.**
- Selection trade count within +/-40% of the control (1,099..2,563); outside that it is a different
  strategy and is reported as such.
- ADDED-vs-REMOVED audit: control trades absent from the variant ("removed") and variant trades with
  no control trade in their span ("added"). Added PF >= removed PF in E1 AND in E2, and added
  PF >= 1.0 overall.
- The PF lift must stay > 0 after excluding entries 09:30-09:35 ET from both variant and control
  (otherwise it is an open-bar clock effect, which belongs in a size-tilt test, not an entry rule).

**Kill criteria.** Any S-clause fails at the centre; either neighbour fails S9 or the three non-off
cells disagree in the sign of PF lift; added PF < removed PF in either era; top-20 retention < 17;
E2 PF lift <= 0; the gain disappears without the 09:30-09:35 entries.

---

## 6. H-E CONDITIONAL STACK (run only if two or more of H-A..H-D pass section 4 and 5 in full)

**Pairing rule, fixed now.** If exactly two pass, stack those two. If more than two pass, stack the
pair whose two features have the lowest absolute Spearman correlation on the control's 1,831
selection signal bars (outcome-blind; H-D's feature is `V/B`); a tie goes to the pair containing
the parent with the larger selection win lift. Only one stack is ever run.

**Rule.** Both parents' masks ANDed (H-D, if a parent, also switches the 20-bar test off).

**Cells (5).** Stack centre = both parents at their centres. Neighbours = one parent moved one grid
step either way with the other at its centre (4 cells).

**Pass bar (selection, vs the knob-off control unless stated).**
- The stack centre clears S1-S8 and S10-S12 (S12 uses the SAME shift k for both masks, so their
  co-alignment is kept and only alignment with the trades is broken). S9 is replaced by the
  3-of-4 neighbour rule below.
- It beats the BETTER parent's centre (higher selection win rate, tie -> higher PF) by win +0.5 pt
  and PF +0.02, with net >= 95% of that parent's net (the house stacking rule: beat the better
  parent, not the control).
- At least 3 of the 4 neighbour cells clear the S9 neighbour bar.
- Every calendar year 2011-2024 keeps >= 50% of the control's selection trade count.

**Kill criteria.** Fails to beat the better parent; fewer than 3 of 4 neighbours hold; any year
starves below 50%; joint null p > 0.01; era D net falls more than 10%.

---

## 7. Order of work (sequential gatekeeping; every clause must pass, so gating adds no false passes)

1. **Build the sibling file in the worktree, then the parity gates. Nothing else is read until all
   pass.**
   - G1: all knobs OFF at R2 settings reproduce `ENGUQ_1M_ETH_R2_1_0.py` trade for trade: whole
     window 1,949 / $613,126; selection 1,831 / PF 1.717 / $524,745 / DD $38,687.
   - G2: all knobs OFF at R5 settings reproduce `ENGUQ_1M_ETH_R5_1_0.py` trade for trade: 2,585 /
     $566,907; selection 2,434 / $466,910.
   - G3: each centre cell, compiled vs interpreted (`EDGELOG_NO_FASTLOOP=1`), identical trade
     counts, entry bars, exit bars, entry prices and per-trade P&L over the full window; extend
     `tests/test_fastloop_parity.py`-style checks to the four knobs.
   - G4-A..D: the feature parity gates in section 5.
   - G5: `tools/exec_feasibility_audit.py --config` passes for each centre cell.
   - A parity failure is fixed and re-run; it is not a hypothesis result.
2. **Run all 12 grid cells plus the control at R2 settings.** Print every cell's full `measure()`
   row, pass or fail, before applying any clause.
3. **Apply S1-S9 and the section-5 extras to every hypothesis.** A0 is checked first.
4. **For hypotheses still standing only:** S10 cost stress, S11 R5 replication, S12 null
   (1,000 draws each, <= 4 processes).
5. **H-E** if two or more pass step 4.
6. **The single LB look** (section 8) for each hypothesis (and the stack) that passed everything.
7. **Write-up:** every cell, every clause with its number, the scan-vs-file gaps, the diagnostics,
   and plain statements of which hypotheses are dead. Drivers and result files saved under `tools/`
   and `tools/r37_results/` in the worktree. No re-runs with changed thresholds, cells or
   definitions; any new idea is the next round's pre-registration.

---

## 8. The single LB look (after every selection decision is final)

- **Who gets it:** only hypotheses (and the stack) that passed sections 4-6 in full. The frozen
  centre cell only; no neighbour, no other cell, no other setting ever touches the LB.
- **How:** `tools/queue_guard.py` on `ENGUQ_1M_ETH_SEL_1_0.py` with every parameter explicit, pinned
  window 2010-06-07..2026-06-30, `db_noadj_eth`, cost 0.533, continuous run, entry-sliced at
  2025-06-30. The reload-graded lockbox is printed for the record and never used. The tail/beta
  block from `--tail-enforce` reads the full window including the LB year, so it is reported only.
- **Pre-declared reading, "LB does not contradict":** verdict not ARTIFACT (a SUSPECT warning is
  printed with its reason); LB trades >= 90; LB net > $0; LB PF >= 1.475 (control 1.675 - 0.20);
  LB win rate >= 26.0% (control 28.0% - 2 pts).
- **Consequences:** pass -> "selection pass, LB does not contradict", forwarded to the owner as a
  candidate for a fenced single-hypothesis Auto-Validate (auto_expand false, walk-forward folds
  >= 6/8) plus a continuous cross-check and a forward paper leg beside `ENGUQ_335`. Fail ->
  "selection pass, LB contradicts", not forwarded, no re-tuning.
- **The LB never chooses.** If more than one hypothesis survives, their order was already fixed by
  the selection window: larger selection win lift first, then larger PF lift. The LB figures are
  printed beside the control's (118 / 28.0% / 1.675 / $88,380 / DD $41,534) and nothing is re-ranked.

---

## 9. Multiple-testing accounting

| item | count | adoptable? |
|---|---|---|
| Primary grid cells at R2 settings (4 hypotheses x 3 non-off values) | 12 | only the 4 centre cells |
| Control runs (R2 knob-off, R5 knob-off, R2 at 0.783) | 3 | no |
| Cost-stress cells at 0.783 (centres of survivors) | <= 4 | no (gate only) |
| R5 replication cells (centres of survivors) | <= 4 | no (sign gate only) |
| Conditional stack cells | <= 5 | only the stack centre |
| Day-shift null backtests | <= 5 x 1,000 | no |
| LB looks (continuous, entry-sliced) | <= 5 | no (confirmation only) |

- **Decisions that can declare a winner: at most 5** (four centre cells and one stack centre).
  There is no argmax over cells: the adoptable cell per hypothesis was fixed above, and the
  neighbours can only veto.
- **Null threshold:** Bonferroni 0.05 / 5 = **0.01 per decision**, required separately on the win
  lift and on the PF lift. Under a global null, the chance that any decision passes S12 is at most
  5%, before the effect-size (S1-S3), concentration (S5), era (S6), plateau (S9), cost (S10) and
  replication (S11) clauses, each of which can only lower it.
- **What this does NOT correct for, said plainly:** the four features were chosen from a 160-feature
  screen on the same selection trades (anatomy within-year BH q: H-A 0.007, H-B 0.020, H-C 0.045;
  H-D 0.21, not a survivor). The in-engine null is not independent of that screen, so expect the
  real effect to be smaller than measured here (winner's curse). Walk-forward folds and forward
  paper are the only answers to that.
- **Power, stated before the run:** removing ~200 signals at random moves the kept win rate by about
  +/-0.4 pt (one standard deviation), so a +1.0 pt real lift clears p <= 0.01 only if the in-engine
  effect is close to or above the scan's. A near miss is reported as a near miss and stays dead.

---

## 10. Rejected ideas (not tested this round)

**From the location lens**
- **Session-high proximity (room to the session high in R):** post-hoc outside the FDR screen,
  p 0.05, non-monotone (the nearest fifth wins only 27.5%), and Spearman -0.57 with H-C's recovery,
  so it is mostly the same factor.
- **Structure height floor (% of price):** it is the volatility factor (Spearman +0.84 with
  ATR%price; the ATR-unit height has no signal, p 0.74) and a fixed % floor starves quiet years
  (2017 keeps 58%); H-A tests that factor era-neutrally.
- **Location stack as proposed (recovery x stretch 3x3):** replaced by the generic conditional
  stack H-E, which only runs if two parents pass on their own.

**From the imbalance lens**
- **Spike candle (range >= 1.0 ATR and/or clock volume as an extra AND filter):** neither half is
  FDR-significant (range q 0.17), candle shape is flat or inverted, the primary cell's post-hoc win
  lift was +0.4 pt overall and -0.5 pt in E2; the volume half is tested more cleanly as H-D.
- **Rebound climax veto (recovery-leg vs decline-leg clock volume):** no anatomy support; found by a
  six-feature post-hoc probe where "worst bucket in both eras" happens ~20% of the time by chance;
  non-monotone; only 47 vetoed E2 trades; needs a new compiled helper.
- **Up-volume / up-bar share:** a doji tick-grid artifact (doji share 13% in E1 vs 3% in E2,
  Spearman -0.65); the doji-excluded version is flat or inverted in E2.
- **"The candle that breaks" (fresh crossing of the decisive level):** does not win more (28.7% vs
  29.6%, PF(R) 1.29 vs 1.46).

**From the context / timing lens**
- **Re-fire shallow limit:** needs a kernel change in the compiled walk, the R2 base's eras disagree
  (E2 re-fired +0.26 R vs single-print +0.42 R), the only evidence is on trades that DID fill, and it
  runs against the measured deeper-limit finding.
- **Trendline drawn in a dead tape:** the same ATR-percentile factor as H-A read over the structure
  window; on the R2 base its own removals disagree across eras (E1 +0.18 R vs E2 -0.42 R) and it
  removes 9 of the 36 best-R trades.
- **Re-entry cooldown port to the crown:** on R2 the 28 re-entries within 10 bars of an exit made
  +$26.8k, so there is nothing for a cooldown to remove.
- **Dip context (below the 20/50/200-day SMAs, low daily RSI, days since a 20-day high):** carried by
  2010-2019 only (E2 p 0.17-0.72) and next to the dead trend-level regime family; H-B keeps the one
  daily-location read that is independent of volatility.
- **VIX prior close / calm-VIX floor:** the same volatility factor as H-A, needs aux-data plumbing
  in the engine, and calm-VIX trades still make +$82k after H-A's cut.
- **Planned-risk % floor:** the same factor as H-A; kept only as H-A's reported diagnostic.
- **Session or clock filters (overnight vs cash, time of day):** pass net R only, i.e. the fixed
  cost weighing more on small overnight stops; they fail the win and gross-R tests.
- **Prior-day high/low, round numbers, trendline R^2 / slope / lower-high count, breakout size,
  body/wick/close location, the file's own volume ratio:** no win or gross-R signal (p 0.07-0.90).
- **A combined model of the features:** logistic AUC 0.513 / 0.536 across periods; the model is not
  the lever (and the ML gate family is closed).

**From the untested list, not ready this round**
- **Order-flow delta:** no data until ~October 2026. **Megacap earnings calendar:** no data source in
  the engine. **gap_pct / NQ-vs-ES relative strength:** single-run curiosities that need aux data.
- **Limit 0.85 + cap 8,280 cell:** not an entry rule, and its LB has already been read.
- **Search-space hygiene (dead `buf_atr`, powerless `er_len`):** an owner call, not a hypothesis.
- **Exits, stops, sizing, shorts, other bar sizes, ES, overlays:** closed by the dead-end library and
  outside the owner's framing.

---

## 11. Deviations

(Append-only. Each entry: date, what changed, why, and which results were already visible when it
changed.)

### 2026-09-14 - order of work item 1 (sibling file + parity gates G1-G5)

Results visible when these were decided: none. No grid cell had run; the only numbers seen were the
parity-gate readings (knob-off controls, which equal the published frontier rows, and trade-list /
feature identity checks that print no variant performance). No threshold, cell, definition or order
of work was changed.

1. **DEFAULT_PARAMS ranges (ambiguity).** Section 2 says "copy of R5 with DEFAULT_PARAMS reset to
   the R2 defaults" but gives no ranges. R5's fence (limit_atr 0.70-1.00, max_hold_bars 6,900-12,000)
   would put the R2 defaults outside their own range. Reading: the 14 R2 knobs carry R2's own
   DEFAULT_PARAMS entries (default and range); max_hold_bars defaults to 0 with its min lowered to 0
   (max 12,000, step 460, which contains 9,660); each new knob's range spans exactly its
   pre-registered grid. No result depends on ranges: every run passes every parameter explicitly.
2. **Memo key (safety extension).** Section 2 keys the knob-free arrays by (bar count, first and last
   timestamp, volume nbytes). That key is identical for two different tapes of the same shape (NQ and
   ES on the same window; two synthetic test tapes), which would silently hand one tape's mask to the
   other. The key also carries the timezone, the volume sum and a price fingerprint (first and last
   close, two sampled high/low values, sum of closes); the recovery ratio is also keyed by tl_len. On
   any single tape this changes no value (the gates prove the masks equal fresh recomputation).
3. **vol_clock with no volume array (unspecified).** Literal reading of "a NaN baseline FAILS": every
   signal fails, so the run has no trades. The file does not raise for this case; it does raise for a
   session-keyed knob without `index`, as written.
4. **`_mask_override` semantics (unspecified detail).** It replaces the AND of every enabled rule mask
   (one knob in a single-hypothesis run; for H-E the driver ANDs both shifted masks and passes the
   result). It raises if no rule knob is on. The missing-`index` raise still applies when an override
   is given (literal). H-D's switch of vol_mult to 0 still applies under an override.
5. **`_signal_index_probe` placement.** Appended at the same point as the existing `_signal_probe`
   (after every entry filter including the rule mask, before the limit is placed); like the other
   probes it forces the interpreted walk.
6. **G5 reading (ambiguity).** `exec_feasibility_audit.py --config` is a lookup table of files from the
   2026-08-11 sweep; for this new file it prints "warn UNAUDITED ... audit by hand before crowning"
   and exits 0. "Passes" is read literally as exit 0 / verdict not LEAK. Because config mode does not
   inspect the file, G5 was supplemented (not replaced) by: the file-level static scan
   (PASS, 0 failures, 0 warnings); an interpreted `_signal_index_probe` run per centre cell (0 signal
   bars failing their own mask; probe walk == compiled cell); and a truncation check at two cut bars
   (every feature on the prefix frame == the full-frame feature on those bars).
7. **Added strictness, reported.** G1 also compared every selection-side `measure()` field with
   `r57_frontier.json` row 1 (G2: row 9) and the SEL control's interpreted walk with its compiled walk;
   G3 also required each centre cell's trade list to differ from the knob-off control (a knob that
   removed nothing would make the compiled/interpreted identity vacuous); G4 also fed each helper-built
   mask back through `_mask_override` and required the identical knob-on trade list, so the features
   compared against the CSV are provably the ones the engine uses.
8. **G4-B note.** The CSV has 3 NaN rows for `ta_lvl_sma20d_atr`; the in-engine feature is NaN on 1 of
   them (a first-20-sessions warm-up bar) and finite on 2 (signals on a session's last bar, which the
   anatomy NaN'd because trade_anatomy reads the day row at signal+1). The gate is on the 1,828
   non-NaN rows, as pre-registered; the in-engine value uses the signal bar's own session, as the rule
   in section 5 defines.
9. **Beacon.** The gate driver was wrapped in `tools/research_beacon.py` (one job record); runtime 104 s.

### 2026-09-14 - order of work items 2-3 (grid + S1-S9), readings fixed BEFORE any grid cell ran

Results visible when these were decided: none from the grid. Only the parity-gate readings above
(knob-off controls) had been seen. Driver: `tools/r57_grid.py`; these readings are written into its
docstring (a-j) and were fixed before its first run. No threshold, cell, definition or order of work
was changed.

10. **LB discard vs "whole-window numbers (reported)" (conflict).** Section 3 lists whole-window
    numbers as reported; section 2 (and 8) say LB trades are discarded the moment the engine returns
    and are not printed until section 8. The stricter rule wins: only selection trades are passed to
    `measure()`, so its `lb` block is empty and `whole` / `corr_all` / `hold_all` merely repeat the
    selection read and are not printed. The knob-off control's selection fields must still equal
    frontier row 1 (hard stop), which proves the slice changes no selection number.
11. **Thresholds from exact control values.** S1 = control win + 1.0 pt, S2 = control PF + 0.02,
    S3 = 0.95 x control net, S4 = 0.95 x control MAR ("control - 5%" read as relative), S5a = control
    era share + 2.0 pts, S5c = control TTZ - 2, S7 = control corr + 0.05, S9 PF = control + 0.01,
    S9 net = 0.90 x control. The table's rounded figures (30.4%, 1.737, 0.86, 64.1% ...) are displays.
12. **Retention and trade-set audit (definitions).** Top-20 / top-10: the control's best selection
    trades by $ (stable sort); retained if a variant selection trade's entry bar lies in the control
    trade's [entry bar, exit bar]. "Removed" = control selection trade with no variant trade of the
    same entry bar, exit bar and entry price. "Added" (H-D) = slot refill (section 3) = a variant
    selection trade with no control selection trade whose entry bar lies inside the variant trade's
    [entry bar, exit bar] (the mirror of the S8 span test). "Re-timed" = neither.
13. **What gates (ambiguity).** Gating = S1-S8 at the centre (S8 >= 18 for H-A), S9 on both
    neighbours, every section-5 extra clause that states a condition, and every section-5 kill
    criterion evaluable before S10-S12. H-C's "reported mechanism check: the gap-through fill share
    ... must not rise" is read as GATING (it says "must" and, unlike H-A's diagnostic, is not labelled
    "not a gate"). H-D's +/-40% trade-count clause (1,099..2,563) is GATING. H-A's planned-risk floor
    and session-bucket shares are reported only. Neighbours are shown against S1-S8 for the record and
    veto only through S9 (and, for H-D, the three-cell PF-lift sign agreement).
14. **Gap-through fill (H-C)** = the anatomy's definition: entry price < resting limit - 1e-9, read
    from the interpreted walk's locals (fill probe); that walk must equal the compiled trades.
15. **H-D 09:30-09:35** = entry bar ET clock 09:30 <= hh:mm <= 09:35, inclusive, removed from both the
    variant's and the control's selection trades before PF.
16. **H-A planned-risk diagnostic.** risk% = (limit - swing_low) / limit per bar, limit = c - 0.55 x
    the file's ATR52 (NaN -> TR), swing_low = min(l[i-206..i]). Floor = the value removing
    round(share x N) of the control's selection signals (interpreted signal-index probe, signal bar <
    split), share = the H-A centre mask's rejection share on the same signals. Run with quiet_pct=20
    and `_mask_override` = the risk-floor mask. Session buckets by the signal bar's ET clock: Asia
    18:00-03:00, Europe 03:00-09:30, cash 09:30-16:00, other 16:00-18:00.
17. **Four eras** by entry time: A < 2014-01-01, B < 2018-01-01, C < 2022-01-01, D < 2025-06-30; win
    and PF per era on $ after cost.
18. **Post-run note (written after items 2-3 ran; nothing above was changed).** No new deviation arose.
    None of readings 10-17 decided a verdict: all four centre cells fail S1 (win lift H-A +0.71,
    H-B +0.66, H-C +0.02, H-D -0.40 pts against +1.0), which also fails under the table's rounded
    30.4%. H-C's gap-through clause and H-D's trade-count clause both passed, so reading 13 was not
    pivotal. One of the control's top-20 trades exits after the split (reading 12); no verdict rests on
    S8. The knob-off control reproduced frontier row 1 on every selection field from selection-only
    trades, and its interpreted probe walk matched the compiled trades (153 gap-through fills, as in
    the anatomy). A0 did not trip on any centre. Runtime 26 s, wrapped in the research beacon (one job
    record). Survivors of S1-S9 + section-5 extras: none, so S10-S12, H-E and the LB look do not run.

### 2026-09-14 - order of work item 7 (write-up), after both independent verifiers

Results visible when these were decided: ALL of items 1-3 (every cell, every clause) and both
verifier reports (recompute + look-ahead: confirmed, 0 disagreements; protocol: confirmed, five LOW
findings). Nothing below changes a threshold, cell, definition, verdict or the order of work. No
verifier finding was HIGH and none changes a conclusion. Write-up: `tools/r37_results/r57_summary.txt`,
generated by `tools/r57_summary.py` (runs no backtest; copies every number from
`r57_sel_parity_gates.json`, `r57_grid.json` and `verify_r57_grid.json`; only the protocol verifier's
findings, which exist solely as its report, are typed in).

19. **Null p-values and the LB look (item 7 asks for them).** Section 7 items 4-6 run only for
    hypotheses still standing after item 3, and none were. Literal reading: S10, S11, S12, H-E and the
    LB look did not run, so no null p-value and no LB figure exists for any variant. The write-up
    reports them as "not computed", never as passed or failed. The LB stayed unread for every variant
    (grid `lb.n` = 0 in all 13 cells).
20. **H-A planned-risk diagnostic wording (protocol verifier finding a; reported, not a gate).** The
    section-5 text says "If it matches H-A's win and PF lift, the write-up says H-A is the known
    big-stop / volatility factor", with no tolerance for "matches". Measured: floor win lift +0.874 /
    PF lift +0.0088 against H-A's +0.708 / +0.0081; the floor removes the same NUMBER of control
    signals (235 of 2,464) but only 112 of the same signals. Reading adopted after seeing these
    numbers, so stated as a soft reading: the lifts are of the same order, so the write-up says H-A's
    small lift is "consistent with" the known big-stop / volatility factor, not that H-A "is" that
    factor. The items 2-3 hand-off phrase "removes the same 235 of 2,464 control signals" is corrected
    to "the same count, 112 of them the same signals". No verdict involves it (H-A fails S1, S2, S9).
21. **H-D added / removed definitions (protocol verifier finding b).** Reading 12 stands. The verifier's
    alternatives: "added" = no control trade overlapping the variant trade gives 17 trades (PF 0.031);
    "removed" = no variant entry inside the control trade gives 388 trades (PF 0.903). X-addE1, X-addE2
    and X-addPF fail under all three readings; only the size of the stated mechanism depends on the
    reading. Reported beside the driver's numbers.
22. **G5 (protocol verifier finding c).** Already reading 6. The write-up describes G5 as a hand audit
    (static file scan, per-centre signal-bar probe, two-cut truncation check), not as a pass from
    `exec_feasibility_audit.py --config`, which printed "warn UNAUDITED" and exited 0.
23. **S8 on selection trades only (protocol verifier finding d).** Already reading 12. One control
    top-20 trade exits after the split; counting only variant selection trades can only lower
    retention, every centre passes S8 (H-A 20, H-B 19, H-C 20, H-D 17), so no verdict moves.
24. **Research beacon vs "no Firestore writes" (protocol verifier finding e; bookkeeping).** Section 2
    ties the beacon to runs over ~2 minutes when the session may write Firestore, and its last bullet
    says no Firestore writes. The launching task explicitly permitted the beacon (one job record per
    wrapped run). It wrapped item 1 (104 s), items 2-3 (26 s, below the ~2 min trigger) and the
    recompute verifier (821 s): three job records, no other Firestore writes. Item 7 wrote none.
25. **ENGUQ.md placement (instruction "after the crown sections, before section 1").** Literal
    placement: immediately after the last subsection belonging to the crown sections ("2026-09-08: R2
    sibling measured continuously") and before the `---` divider that opens section 1, plus one dated
    line in the doc's section-3 changelog, which is how that doc records every change. The doc's
    opening paragraph (which still names #309 as the crown as of 2026-09-05) was not edited: out of
    this round's scope.
26. **Conditional deliverables not produced.** The fenced single-hypothesis file (R6-style name) and
    `tools/queue_r57_validate.py` are required only if a hypothesis fully survives (selection + gates
    + LB not contradicting). None did, so neither exists.
27. **Still uncommitted.** Section 2 forbids commits in this round; the section-11 appends, the sibling
    file, tests, drivers, results and the ENGUQ.md section remain uncommitted in the worktree for the
    owner's decision.
