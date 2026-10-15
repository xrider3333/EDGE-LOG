# PRE-REGISTRATION - SUPERSCALPER r1: the public "NQ/MNQ Super Scalper [BACKTEST]" on our NQ 1-minute data (TV, MANAGER GO 10-12 / owner 10-14 #116)

Written 2026-10-14 by TV BEFORE any number from the port exists (the port is still being written; no trade, P&L or count read).
Family: MISC (a public script spanning many families). Second check: STRATEGY-BEATING (#113), verdict due before the
walk-forward read.

## The claim being tested
TradingView strategy by Crispigino (open source, pine-facade PUB;46d5b263 v1.0, photographed 2026-10-14:
`C:\EdgeLog\_research_cache\tv_scalp\superscalper\NQ_MNQ_Super_Scalper_v1.pine`, sha256 5b8a1304..., provenance.json beside it).
Author's own backtest: MNQ 1-minute, one year, 2,934 trades, 63.7% wins, profit factor 1.23 after 2 ticks of slippage a side and
$0.62 a contract; pyramiding 20 (its comment says 6). 3,292 lines: six entry paths scored by an 8-factor confidence engine, about
60 sub-systems, structural stops capped at 3 ATR, nine early exits. TV SCALP MAP (ledger 2.147): the only public scalper whose own
numbers survive costs and a 75% haircut - everything else on the list closed at the map.

## Stage 0 - port fidelity (must pass before Stage A is read)
- Port: `augur_strategies/MISC_SUPERSCALPER_1_0.py` (every input a knob at the author's default; cross symbols: ES1! from the ES
  1-minute no-adjust master, SPY NOT held so ES stands in for SPY (knob spy_proxy), QQQ from the Alpaca 1-minute master).
- Reference: the TradingView "List of Trades" export of the unmodified public script on an MNQ1! 1-minute chart (obtained by the
  OWNER - adding the script to a chart and exporting are account actions; the file goes to the folder above).
- Comparison mode: the port in TradingView's own fill model (knob intrabar = 'tv'), TradingView's 2-tick slippage and $0.62 commission,
  on the export's own dates (recent months, after the lockbox year - never the lockbox).
- PASS: at least 80% of TradingView's trades matched by side and entry minute (+/- 1 bar) AND the matched pairs' per-trade P&L
  correlation at least 0.80. Anything less = FIDELITY FAIL: the gaps are listed; ONE documented repair round is allowed, re-checked
  on the same export; a second fail ends the item with "port could not reproduce the script" (no Stage A verdict claimed).
- If the owner cannot provide the export, Stage A may still run, labelled "UNVERIFIED PORT" on every number.

## Stage A - the published defaults on our data (walk-forward only)
- Data: NQ 1-minute ETH no-adjust master (NOADJ_NQ_1m_ETH, id 34), 2016-07-01 .. 2025-06-29, loaded with a hard date_to (the
  lockbox year 2025-06-30 .. 2026-06-30 is never in memory in Stage A).
- Fills (house): signal on the bar's close, market entries at the next bar's open, stops / limits from the bar after entry; a bar
  holding both a ticket's stop and its target = the STOP first (intrabar = 'worst'). The 'tv' path is reported beside it, never a
  pass route. Forced flat before each no-adjust roll seam; trades open at the end of data dropped.
- Costs: commission + 1 tick slippage each side = $14.12 a round trip per NQ contract = 0.706 points (owner rule 10-12); a stress
  line at +0.25 point. One contract per ticket; concurrent tickets up to the script's own cap.
- Report (house rule): ROC %/yr at $30k drawdown, DD5, DD% from peak, Sortino; plus win rate, average win / average loss, trades a
  year, years positive / negative; the share of net from the best 5% of days; correlation of daily P&L with #463.
- Read: DEAD if WF ROC@30k < 15 (the MDL map line) or net profit factor < 1.0. Otherwise it goes to the Auto-Validate below.
  Per the owner's 10-14 order the Auto-Validate is queued regardless of the Stage A read, so the full search is on the board;
  a Stage A DEAD stays the verdict unless the Auto-Validate's walk-forward clears the same line.

## Auto-Validate (owner 10-14: "autovalidate ... the top 3"; MANAGER #116)
- The ranged port file (never a pinned copy), 900 trials (owner rule, never lower), NQ 1-minute ETH no-adjust master pinned by
  filename (NOADJ_NQ_1m_ETH.csv), window pinned in the job (date_from 2016-07-01, date_to 2026-06-30: the house split, the final
  year is the lockbox stretch read once by the validate itself), cost 0.706 points, intrabar 'worst'.
- Reported: run number, the four numbers for WF and LB apart, PBO, DSR, and the same win-rate / average-win lines.
- Runtime guard: if one full-window trial takes so long that 900 trials cannot finish in about two days, TV stops BEFORE queueing
  and reports the timing to MANAGER (the 900-trial rule is the owner's; a shorter window or a coarser timeframe would need his call).

## Could fool us
- A 3,292-line script ported by hand can differ in many small ways; Stage 0 is the guard, and its window is short.
- The author's year is MNQ on TradingView's data; ours is NQ (same index, ten times the size) on the no-adjust master.
- 20 stacked tickets make one bad day many losing trades at once; DD5 and the best-5%-of-days share are printed to show it.
- SPY is replaced by ES in the relative-strength factor; QQQ exists only in regular hours (carried forward overnight).

## Amendment 1 (2026-10-14, before any port number; MANAGER #118)
- The reference is the AUTHOR's published Strategy report (not a fresh chart run): 274 trades on MNQ1! 1-minute, entries
  2026-03-29 .. 2026-04-21, 1 contract, published settings (pyramiding 20, 2 ticks slippage, $0.62 a contract); trade 274 still
  open (excluded). File `superscalper_tv_trades_published.csv` in the folder above (MANAGER export of the page's report).
- Its times are CHICAGO (exchange) time: checked on the first three entries against our NQ 1-minute bars - each TradingView entry
  equals the open of the bar one hour later in New York time plus / minus the 2-tick slippage. (A data check on three prices, no P&L.)
- That window lies INSIDE the lockbox year (2025-06-30 .. 2026-06-30). To keep the lockbox read for the Auto-Validate alone, the
  fidelity harness prints ONLY match statistics: share of TradingView trades matched, share of port trades matched, entry / exit price
  differences in ticks, exit-reason agreement and the matched pairs' P&L correlation. It never prints the port's own totals, win rate,
  net or drawdown on that window, and nobody reads them. The pass rule above is unchanged (80% matched AND correlation >= 0.80).

## Amendment 2 (2026-10-14, after the Stage 0 FAIL, before any improvement number; owner GO via MANAGER #119)
Everything below is OUR PORT ("MISC_SUPERSCALPER"), not the published script (Stage 0 showed the port cannot reproduce it).
- ONE improvement round on the DEVELOPMENT YEAR only: NQ 1-minute ETH no-adjust, 2024-01-01 .. 2024-12-31 (already read once, as
  ported: net PF 0.962, 68.8% wins, average win 15.5 vs loss 33.4 points - it lost on size, not hit rate). Lockbox unread.
- New knobs (defaults reproduce the as-ported trades exactly; a test pins that): sl_scale (stop distance x, default 1.0),
  max_hold_bars (time-out, 0 = off), be_trigger (move the stop to entry after +k x initial risk, 0 = off), vix_feed ('none' |
  'daily': CBOE daily VIX photograph, the last COMPLETED day's close vs the close 10 sessions earlier, in place of the 1-minute VIX).
  NYSE TICK stays absent (dropped). A footprint stand-in from our 10-second delta export is NOT possible: that capture starts
  2026-06-23, after the development year and the whole walk-forward window.
- The grid, fixed now (108 cells): sl_scale {0.5, 0.75, 1.0} x tp1_mult {2, 4, 6} x max_hold_bars {0, 30, 90} x be_trigger {0, 1.0}
  x vix_feed {none, daily}; every other knob at its default; cost 0.706 points; intrabar 'worst'.
- Selection: the cell with the highest development-year NET profit factor among cells with at least 500 trades. It becomes the
  "improved" defaults ONLY if its net PF beats the as-ported cell's (0.962); otherwise the as-ported defaults stand. Printed for both:
  trades, win rate, average win / average loss, net PF, net points. The best of 108 cells on one year is optimistic by construction -
  the Auto-Validate's walk-forward and lockbox, not this round, decide.
- Auto-Validate (replaces the section above where it differs): the ranged file with the chosen defaults, the new exit knobs OPEN
  (sl_scale 0.4-1.2, tp1_mult 2-6, max_hold_bars 0-240, be_trigger 0-2, vix_feed none/daily) plus the existing ranges, 900 trials,
  NOADJ_NQ_1m_ETH.csv pinned, window 2016-07-01 .. 2026-06-30, cost 0.706, intrabar 'worst', queued behind NOISE #422+TP. Runtime guard
  unchanged. Reported: run number, the four numbers WF and LB apart, PBO, DSR, win rate, average win / loss.

## Amendment 3 (2026-10-14, before any improvement number; NOISE review GO WITH EDITS, C:/EdgeLog/manager/reviews/superscalper_r1_amendment2_review_NOISE_2026-10-14.md)
Accepted in full; replaces Amendment 2 where they differ.
- Units: the as-ported 2024 figures 15.5 / 33.4 are GROSS points per trade; NET at 0.706 they are 14.8 / 34.0 (payoff 0.44).
- E1: the script's "3 ATR hard cap" (Pine lines 687 / 692 / 702 / 707) is a no-op (a stop below the close is always under close +
  3 ATR), copied faithfully - regular-hours stops are uncapped. New knob sl_cap_atr {off = as-ported, 3.0 = the author's stated cap,
  applied}; cap first, then sl_scale.
- E2: tp1_mult only moves a fallback target (the nearest of ~22 structural levels usually wins), so the target axis becomes
  tp_scale {1.0, 1.5, 2.0}: tp = c + (tp - c) x tp_scale on every path, applied after the minProfit entry gate. tp1_mult stays at 4.
- Every exit change applies AFTER all entry gates: entries are the as-ported entries; defaults reproduce the as-ported trades (test).
- The grid (216 cells): sl_cap_atr {off, 3.0} x sl_scale {0.5, 0.75, 1.0} x tp_scale {1.0, 1.5, 2.0} x max_hold_bars {0, 30, 90} x
  be_trigger {0, 1.0} x vix_feed {none, daily}. Breakeven moves the stop from the bar AFTER its trigger bar.
- Daily VIX: `C:\EdgeLog\_research_cache\public_series\cboe_vol_daily.csv`, sha256 9790df06...; non-NQ-session rows dropped (the
  CME-holiday rows from 2022); day D's close usable from 16:15 ET on D; the 10-session lookback counts NQ sessions.
- Selection (stricter): adopt a cell as the improved defaults ONLY if its development-year net PF >= 1.0 AND the median net PF of its
  one-step grid neighbours > 0.962 (a plateau, not one cell); otherwise the as-ported defaults stand. The +0.25-point stress line is
  printed for the chosen cell. The harness checks this file's LF sha256 at start.
- Validate lattice (a development choice must lie on it): sl_scale 0.40..1.20 step 0.05; tp_scale 1.0..2.0 step 0.25; max_hold_bars
  0..240 step 30; be_trigger 0..2 step 0.5; sl_cap_atr {off, 3.0}; vix_feed {none, daily}; the existing knobs keep their ranges.
- The validate's walk-forward read is printed with the 2024 fold shown apart and the chain WITHOUT it (knobs were chosen on 2024).
- Runtime guard, measured before queueing: NOISE timed ~20 s per year of 1-minute ETH (~3 minutes a full-window trial); 900 trials on
  the optimize window plus the walk-forward re-searches likely exceed ~2 days. TV measures on this machine and, if the guard trips,
  reports the timing to MANAGER before queueing (900 trials is the owner's rule; a shorter window / coarser bars need his call).
- Priors stated before the number: NOISE and STRATEGY-BEATING both ~5-10% that the Auto-Validate's WF clears ROC 15.

## Amendment 4 (2026-10-14, before any improvement number; port build questions + runtime guard)
Replaces Amendments 2 / 3 where they differ. No development-year number has been read since Amendment 3.
- Stop cap scope: sl_cap_atr = 3.0 caps ONLY the session stops the author wrote the cap on (Pine 687 / 692 / 702 / 707), i.e. the
  MAIN, BOS and RE tickets; OB and OD keep their own stops, TRAP is self-bounded (<= 2.5 ATR). This is the literal reading of "the
  author's stated cap". sl_scale applies on every path, after the cap.
- Exit mechanics as built: max_hold_bars exits at the open of fill bar + N (before that bar's new entries); breakeven risk = fill price
  to initial stop, a ticket with no positive risk never arms, the stop moves from the bar AFTER the trigger bar.
- VIX session day = a date with a tape bar between 13:00 and 15:59 ET; the value is empty until the tape's first 16:15 and the
  10-session value until its 11th session (cold start, as every indicator).
- VIX file: the improvement round reads the pinned derived file above (the harness passes _vix_file='derived'). The Auto-Validate
  needs VIX through 2026-06-30 (its lockbox stretch) and the derived file stops at 2025-06-27, so the port's default is the raw CBOE
  photograph `C:\EdgeLog\_research_cache\public_series\cboe\VIX_History.csv` (sha256 6edc3e3928c4b164b9e4ed1ec874e0ed53c7d52997557adebb7d6b7451db565a,
  fetched 2026-10-05, in public_series_provenance.json), CLOSE column. Both files are sha-checked on every load and drop every row
  dated after the run's last bar right after parsing; a test pins identical VIX arrays under both files on all of 2024.
- Port mechanics are pinned for the validate: intrabar, close_rule, spy_proxy, footprint and daily_close each offer ONE search option
  (the default; intrabar 'worst'), because the Auto-Validate searches every option of a text knob. The script's own knobs, pyramiding
  and the new exit / VIX knobs keep their ranges.
- Memory (runtime guard): one as-ported trial needed ~1.5 GB per year of 1-minute bars (a full-window trial exhausted free RAM and was
  stopped). The port now releases each working array after its last use - a mechanical edit by `tools/free_locals.py`, values
  untouched; 8 of 8 configurations (defaults + 7 random, new knobs included) give identical trades on 2024 - about 0.2-0.4 GB per year.
  Also an engine fix outside this round: rolls.epoch_seconds no longer boxes every bar time (~2.3 s per year on every backtest call).
- Runtime (MANAGER #122): trials are never cut; after the speed-ups the validate is queued with the measured ETA posted.

## Amendment 5 (2026-10-15, before the Auto-Validate is queued; MANAGER #135)
- New search knob `session_filter` {all, outside_rth, rth}, default all (= the improvement round's defaults, unchanged trades):
  entries only from signal bars outside / inside 09:30-15:59 New York time; exits untouched. It is in the Auto-Validate's search
  space so the 900-trial walk-forward finds or rejects it - it is NOT hand-picked.
- Disclosure: the knob comes from development-year decompositions. r2 E1 (2024): every RTH window lost, outside RTH carried it (PF
  1.085). r2b (2023): the mirror - RTH PF 1.209, outside RTH 1.024. The effect flips sign between the two development years.
- Also disclosed (r2 E0): the improvement round's pick did NOT hold on 2023 (net PF 1.071 vs as-ported 1.073); the validate still
  runs (owner order) with those defaults as its anchor, labelled.
- The walk-forward read prints the folds overlapping 2023 AND 2024 apart, plus the chain without them (both are development years now).
