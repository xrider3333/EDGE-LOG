# PRE-REGISTRATION — order-flow round 1: 10-second delta as a size rule on ORB #314 and NOISE #422 (2026-09-30)

Owner ask via MANAGER (inbox #29): use the order-flow data we already capture but never used, and score anything
found FORWARD with the paired early stop. Written and pushed before any trade outcome was joined to the feature.
Driver: tools/orderflow_r1.py. Early stop: tools/paired_seq_stop.py (read_pair), as in
docs/PREREG_paired_sequential_stop_2026-09-29.md.

## Mechanism
A breakout that is being bought (or sold) aggressively in its own direction is more likely to be carried on by
the flow behind it; a breakout printed against opposing aggressive flow is being absorbed and fails more often.
Order-flow sign is persistent at short horizons (Lillo & Farmer 2004; Chordia, Roll & Subrahmanyam 2002 on order
imbalance and returns). Honest prior: the contemporaneous link is strong and the predictive one is weak, so a
small effect is the realistic best case. This is new INFORMATION (never used by any EL rule), not a new tuning.

## Data
NinjaTrader 10-second NQ bars with buy / sell volume and delta, C:\EdgeLog\ohlc\NQ_10s.csv, 2026-06-23 onward.
Capture has gaps: on ~22 of 70 RTH sessions delta stops for hours while bars keep coming (routed to the
PAPER-NT8 chat, their inbox #23). Trades whose window lacks delta are simply not tilted (1.0x) and do not enter
the early-stop series, so gaps shrink the sample; they do not bias it.

## Feature and rule (read at the signal bar; nothing from the fill bar)
For a trade entering at 5m bar E (bar-open label = fill time): window = the 10s bars that CLOSE by E, from
max(09:30 ET, E - 30 min). Valid when it spans >= 5 min, holds >= 90% of its 10s bars, and >= 80% of those carry
buy+sell volume. Imbalance = sum(delta) / sum(buy + sell); aligned = trade side x imbalance.
- aligned >= theta(L) -> 1.5x; aligned <= -theta(L) -> 0.5x; otherwise, or window not valid -> 1.0x.
- theta(L) = median |imbalance| of every valid RTH window of the same length on the capture before 2026-10-01
  (feature only, no outcome): 5 min 0.0331, 10 min 0.0242, 15 min 0.0206, 20 min 0.0185, 25 min 0.0174,
  30 min 0.0157. One rule, both legs, no alternatives tried.

## Legs (same trades, only the size differs)
- ORB #314 (crown): ORB_3_6_R6.py at #314's settings, NQ 5m RTH db_noadj_rth, cost 0.533, $20/pt.
- NOISE #422 (BOOK #463's NOISE leg): NOISE_1_8_CT304H.py 20 / 1.15 / 1.75x. NOISE #382 (the live primary) is
  the same signal stream re-sized, so its entries and this feature are identical.
Twin = the same leg at 1.0x. Each leg is judged separately.

## Backfill (2026-06-23 .. 09-30) - a KILL check only, never a pass
Frozen before outcomes were read: ORB 33 trades, 29 with a valid window (1.5x on 9, 0.5x on none); NOISE 49
trades, 31 valid (1.5x on 11, 0.5x on 5). With 29-31 tilted trades nothing can be established, so: if a leg's
backfill paired t (below) is <= -2.0, that leg's shadow is not started; anything else starts the forward shadow.

## Forward shadow and verdict
- Forward trades = each leg's backtest-replay trades on the refreshed NQ 5m master from 2026-10-01 (paper fills
  are a cross-check only - both arms share the fill, so execution cannot decide). Scored by the Custom ML chat
  from the 10s file; no lane has to change anything. No orders.
- Paired early stop on valid-window trades: d = (m - c) x trade P&L, c = mean size over the backfill's valid
  trades (reads the feature, not outcomes): ORB c = 1.1552, NOISE c = 1.0968. Looks every 10 from trade 20;
  boundary |t| >= 3.00 for both (sizes drawn independently of walk-forward outcomes cross it 1.9% / 0.9% of the
  time over the full test), and the ex-extreme-trade check at 2.0.
- Final read (unchanged owner yardstick) at 120 forward ORB trades / 150 NOISE trades, or 2027-06-30: the sized
  leg beats its raw twin on ROC %/yr at a $30k worst drawdown valued daily AND on Sortino, and stays ahead
  without its single best trade. ROC at a fixed drawdown is scale-free, so extra size alone cannot pass - the
  rule must sit above the twin's leverage line. A pass is a CANDIDATE for the owner (via MANAGER) and is offered
  to Frontier as a book-leg stream; it adopts nothing by itself.

## BACKFILL RESULT (2026-09-30, run once as registered) - neither leg killed; both forward shadows start 2026-10-01
- ORB #314: 29 of 33 trades had a valid window; paired t +1.23. The 9 trades sized 1.5x made $23,974 raw, the 20
  untilted valid trades $16,694; no ORB trade drew opposing flow (0 at 0.5x).
- NOISE #422: 31 of 49 valid; paired t -0.68. 1.5x trades -$3,155 (11), 0.5x trades -$2,563 (5), untilted
  valid +$28,094 (15); the 18 trades without delta made -$11,636.
- Neither number is evidence (29-31 trades); this only cleared the kill line. Forward read: `python
  tools/orderflow_r1.py forward` (EDGELOG_ROOT = the shared checkout).

## CORRECTION 2026-09-30 (MANAGER #34 re-check) - before any forward trade was read; supersedes the rule above
Found by re-checking the build, not by looking at results:
- **10-second stamps are bar END, not bar open.** Thirty 10s bars stamped 09:30:10 .. 09:35:00 rebuild the 09:30
  5m master bar exactly (open, high, low, close); the open-stamp reading does not. **ORB fills at the CLOSE of its
  entry bar** (close-confirm; the engine's entry price = that bar's close), NOISE at the OPEN of its entry bar.
- The first version therefore ended the window 10 seconds early for NOISE and 5 minutes early for ORB (it left
  out the breakout bar). Never late: no look-ahead in either version. Corrected rule: window = the 10s bars ENDING
  in (start, fill], start = max(09:30, fill - 30 min), fill detected per trade from the engine's entry price.
- theta recomputed on the corrected windows (feature only): 5 min 0.0329, 10 0.0243, 15 0.0208, 20 0.0185,
  25 0.0174, 30 0.0155.
- Early stop = the running-mean form (paired_seq_stop amendment); B 3.00 for both legs (false stops 1.4% / 0.5%).
- **Kill check re-run on the corrected rule** (declared before running; its result stands either way): backfill
  now to 09-30. ORB #314 30 of 34 valid, paired t +0.71; NOISE #422 37 of 55 valid, paired t **-1.89** - neither
  crosses -2.0, so both forward shadows start 2026-10-01. NOISE sits close to the kill line and leans the way
  the ENGU-Q lane's round 64 found on 1-minute breakouts (heaviest agreeing flow persists least) - expect little.
- Overlap: the ORB lane runs its own breakout-bar order-flow shadow on #314 (docs/PREREG_orb_orderflow_shadow_
  2026-09-30.md); the corrected window now contains that bar, so the two ORB reads are NOT independent.
- **Same-contract sessions only (NOISE lane finding, their e78ba46c; added before any forward trade):** a session
  is scored only if >= 80% of the 5m closes rebuilt from the 10s rows equal the NQ master's close exactly - on
  2026-09-14 the capture had rolled to December while the master was still on September. Forward scoring only;
  the backfill kill check is not re-run a third time. On the backfill 65 of 70 sessions pass (dropped 08-18,
  08-19, 09-07, 09-14, 09-15).
