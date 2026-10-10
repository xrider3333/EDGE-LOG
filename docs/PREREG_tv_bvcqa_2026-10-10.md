# PRE-REGISTRATION - BVC QA r1: does a price-only buy/sell split reproduce NinjaTrader's real delta? (TV, MANAGER GO 10-10)

Written 2026-10-10 by TV BEFORE any correlation, delta sum or proxy value has been computed. Reading shelf No. 26 (Easley,
Lopez de Prado & O'Hara 2012, RFS 25(5): bulk volume classification, "BVC"). Data QA only: no P&L, no strategy, no lockbox.
Read so far: the 10s files' header line and their first / last rows (to learn the columns), nothing else.

## Question
The house's order-flow evidence is the NinjaTrader 10-second capture (C:\EdgeLog\ohlc\NQ_10s.csv, ES_10s.csv; columns time,
open, high, low, close, volume, delta, buy_vol, sell_vol, tick_count, rt), live only since late June 2026 and gappy. BVC splits a
bar's volume into buys and sells from the bar's price change alone. If BVC tracks the real delta, the order-flow lane gets a proxy
over the full 15-year bar history; if not, order flow stays forward-only.

## Data (one choice each)
- Markets: NQ (the bar), ES (reported beside it).
- Rows: the 10s files as they stand at the run. `time` = UTC epoch seconds, rows END-stamped (row t covers (t-10s, t]); a row
  belongs to the 1-minute bar whose ET clock interval contains t - 1 s.
- Sessions: RTH 09:30-16:00 ET only. A session is KEPT when its RTH holds >= 95% of the 2,340 possible 10s rows AND >= 95% of
  those rows have rt = 1 (live capture = the ground truth; rt = 0 rows are Tick Replay / headless backfill, approximate or zero).
  DROPPED regardless: 2026-10-08 and 2026-10-09 (MANAGER: the 10-08 feed flap and the 10-09 08:03 chart freeze). Every dropped
  session is listed with its reason.
- Bars: 1-minute (the bar) and 5-minute (reported), built from the kept 10s rows: open = first open, close = last close,
  volume = sum. A bar holding any rt = 0 row or fewer than all its 10s rows is dropped (counted).
- Truth: D = the sum of the 10s `delta` over the bar.

## The proxy (one choice each)
- dP_i = close_i - close_(i-1), the previous bar of the same session; the session's first bar uses close - open.
- sigma_i = the standard deviation of dP over the previous 60 bars (past only, may span earlier kept sessions); a bar with fewer
  than 30 earlier bars is skipped.
- BVC_i = V_i x (2 x Phi(dP_i / sigma_i) - 1), Phi = the standard normal CDF (the paper's original form).

## Statistic and bar (fixed now)
- THE STATISTIC: the pooled Pearson correlation of BVC_i and D_i over every kept NQ 1-minute bar.
- PASS: r >= 0.60 (MANAGER 10-10). FAIL: r < 0.60. No other route to a pass.
- Reported beside it, never a pass route: ES 1-minute; NQ and ES 5-minute; the median per-session r; a bar-level tick-rule twin
  V x sign(dP); the plain price change dP; the share of D's variance BVC leaves unexplained (1 - r^2).

## Reading (decided now)
- PASS: BVC can stand in for delta on history for the order-flow lane. It is built from price and volume only, so anything it
  finds is price-volume information the house has already mined; only the unexplained part of the real delta is new, and that
  part stays forward-only on the NT capture.
- FAIL: closed. Order flow stays forward-only on the NT capture, as now.

## Could fool us
- NT's delta classifies each tick against the bid / ask; BVC sees only the bar. A high r can come from the mechanical link (big
  up bars carry buy-initiated volume), so the dP-alone r is printed to show how much BVC adds over price.
- The capture window is short (about 3.5 months, mostly one regime) and has gaps; per-session r is printed to show the spread.
- The 1-minute bars come from the 10s capture, not from the historical masters; a historical proxy would use the masters, whose
  volume is the same exchange volume but may differ at the seams.

Script: tools/tv_bvcqa_r1.py (committed after this file; it reads nothing but the two 10s files).
