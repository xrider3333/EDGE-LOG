# ENGD — Engulfing Down

> Built from the real trades in EDGE LOG (TRADING LOG ▸ TRADES) and the chart links saved with them. The page is regenerated each time new trades are added, so hand edits here would be lost: change a label or note in TRADING LOG, or ask Claude to correct a reading.

## The rule as written

- The short mirror of ENGU (the owner reads it on an inverted chart): a large-body red candle on a volume spike that engulfs the prior candle(s), at a level with room to the next level down.
- Entry: the next candle's open. Stop: above the trigger candle's high.

## What the data says so far

- 2 trades: one +0.38 R winner at the 09:31 open (2026-05-13), one -0.56 R loss mid-afternoon (2026-05-07, his note: made a higher high). Too few to call.

## Futures — 2 real trades

| Trades | Wins | Net $ | Avg R | Median chase % | Median MFE capture % | Median MAE % of risk |
|---|---|---|---|---|---|---|
| 2 | 1 | -7.55 | -0.09 | 4.7 | — | 56.0 |

| Date | Sym | Dir | P&L $ | R | Chase % | Capture % | Vol × | Body × | Grade | Label from |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-07 | MES | SHORT | -19.40 | -0.56 | 0.0 | — | 2.0 | 3.0 | — | sheet |
| 2026-05-13 | MES | SHORT | 11.85 | 0.38 | 9.4 | — | 13.0 | 6.2 | A | EL |

### Futures trades, one by one

#### 2026-05-07 · MES SHORT 7362.00→7365.50 · -19.40

- **EL trade:** #20 in TRADING LOG ▸ TRADES, 2026-05-07 MES (id …LxdMn9)
- **Label:** ENGD (from the TRADETRACKER sheet — EL has none)
- **Grade · TF:** — · 1m
- **Times (ET):** signal 14:09 · in 14:10 · out 14:12
- **Size:** 1 × MES ($5/pt)
- **Notes:** MADE HH :( (sheet)
- **Chart:** [tOU5oaTk](https://www.tradingview.com/x/tOU5oaTk/) · [png](https://s3.tradingview.com/snapshots/t/tOU5oaTk.png)
- **Snapshot taken:** 2026-05-07 15:34 ET
- **Snapshot shows:** On May 7 he shorted one MES at 7362.00 at 14:10 ET, just after the big 14:09 down bar (7367.25 to 7362.00, high 7368.25), drew a stop at 7368 and a target near 7355.25, and bought back for a loss at 7365.50 at 14:12 after price dipped to 7358.75 and bounced.
- **Drawn on the chart:** entry 7361.75 · stop 7368.00 · target 7355.25
- **Data note:** the exit price 7365.50 is one tick outside the ES bar (7363.00-7365.25): a MES print the full-size contract did not trade
- **Checked:** Chart and bars read, then re-checked by a second, independent pass: every field confirmed

| Signal O/H/L/C | Range | Body % | Body × prior-10 | Vol × prior-10 | Stop | Risk pts | Chase % | R | MAE % of risk | MFE pts | Capture % | Best next 15m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 7367.25 / 7368.25 / 7360.50 / 7362.00 | 7.75 | 68 | 3.0 | 2.0 | 7368.25 | 6.25 | 0.0 | -0.56 | 56 | 0.00 | — | 1.50 |

<details><summary>1-minute OHLC (1-minute CME bars, unadjusted)</summary>

| 1m ET | O | H | L | C | Vol | |
|---|---|---|---|---|---|---|
| 13:54 | 7350.00 | 7353.25 | 7349.75 | 7352.75 | 2652 |  |
| 13:55 | 7352.75 | 7355.75 | 7352.75 | 7354.50 | 3313 |  |
| 13:56 | 7354.50 | 7361.50 | 7351.25 | 7358.75 | 11502 |  |
| 13:57 | 7358.50 | 7362.00 | 7358.25 | 7360.75 | 5912 |  |
| 13:58 | 7360.75 | 7362.50 | 7360.00 | 7362.00 | 2699 |  |
| 13:59 | 7362.00 | 7366.25 | 7362.00 | 7365.25 | 3774 |  |
| 14:00 | 7365.25 | 7366.75 | 7363.75 | 7365.00 | 3948 |  |
| 14:01 | 7365.00 | 7365.75 | 7362.00 | 7362.75 | 2922 |  |
| 14:02 | 7362.75 | 7364.50 | 7359.50 | 7364.25 | 5136 |  |
| 14:03 | 7364.25 | 7364.75 | 7361.25 | 7362.50 | 2088 |  |
| 14:04 | 7362.25 | 7364.50 | 7361.25 | 7363.00 | 3075 |  |
| 14:05 | 7363.00 | 7366.00 | 7363.00 | 7365.75 | 1423 |  |
| 14:06 | 7365.75 | 7367.75 | 7365.25 | 7367.50 | 2487 |  |
| 14:07 | 7367.50 | 7369.75 | 7366.25 | 7369.00 | 2586 |  |
| 14:08 | 7369.00 | 7369.75 | 7366.50 | 7367.25 | 1836 |  |
| 14:09 | 7367.25 | 7368.25 | 7360.50 | 7362.00 | 5944 | SIGNAL |
| 14:10 | 7362.00 | 7364.00 | 7358.75 | 7363.75 | 3296 | IN 7362.00 |
| 14:11 | 7363.75 | 7365.50 | 7362.25 | 7364.25 | 3028 |  |
| 14:12 | 7364.25 | 7365.25 | 7363.00 | 7364.75 | 1567 | OUT 7365.50 |
| 14:13 | 7364.75 | 7365.25 | 7362.25 | 7364.25 | 1596 |  |
| 14:14 | 7364.25 | 7365.50 | 7363.00 | 7364.50 | 1209 |  |
| 14:15 | 7364.75 | 7366.50 | 7364.25 | 7366.00 | 1398 |  |
| 14:16 | 7365.75 | 7366.75 | 7365.00 | 7365.25 | 1452 |  |
| 14:17 | 7365.50 | 7368.25 | 7365.50 | 7367.75 | 1370 |  |
| 14:18 | 7368.00 | 7370.50 | 7368.00 | 7369.75 | 3228 |  |
| 14:19 | 7369.50 | 7370.25 | 7366.25 | 7366.75 | 2057 |  |
| 14:20 | 7367.00 | 7368.50 | 7365.75 | 7366.50 | 2385 |  |
| 14:21 | 7366.75 | 7367.50 | 7366.00 | 7366.00 | 1037 |  |
| 14:22 | 7366.25 | 7368.75 | 7365.25 | 7365.75 | 1598 |  |
| 14:23 | 7366.00 | 7366.25 | 7363.75 | 7364.25 | 1632 |  |
| 14:24 | 7364.25 | 7365.25 | 7362.50 | 7363.00 | 1452 |  |
| 14:25 | 7363.00 | 7363.00 | 7360.75 | 7361.00 | 2544 |  |
| 14:26 | 7361.00 | 7363.50 | 7360.75 | 7362.75 | 1499 |  |
| 14:27 | 7363.00 | 7363.00 | 7360.50 | 7361.75 | 1688 |  |

</details>

#### 2026-05-13 · MES SHORT 7422.25→7419.50 · +11.85

- **EL trade:** #22 in TRADING LOG ▸ TRADES, 2026-05-13 MES (id …LpOXQf)
- **Label:** ENGD
- **Grade · TF:** A · 5s
- **Times (ET):** signal 09:30 · in 09:31 · out 09:31
- **Size:** 1 × MES ($5/pt)
- **Notes:** good managment
- **Chart:** The chart saved with this trade (tOU5oaTk) shows the 2026-05-07 14:10 ENGD short, not this one; no snapshot of this trade exists.
- **Checked:** No chart of this trade; times, signal and stop from the bars, re-checked by a second, independent pass

| Signal O/H/L/C | Range | Body % | Body × prior-10 | Vol × prior-10 | Stop | Risk pts | Chase % | R | MAE % of risk | MFE pts | Capture % | Best next 15m |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 7429.25 / 7429.50 / 7421.50 / 7423.00 | 8.00 | 78 | 6.2 | 13.0 | 7429.50 | 7.25 | 9.4 | 0.38 | — | — | — | 16.00 |

<details><summary>1-minute OHLC (1-minute CME bars, unadjusted)</summary>

| 1m ET | O | H | L | C | Vol | |
|---|---|---|---|---|---|---|
| 09:15 | 7431.25 | 7432.75 | 7431.25 | 7432.75 | 496 |  |
| 09:16 | 7432.50 | 7432.75 | 7432.00 | 7432.75 | 249 |  |
| 09:17 | 7432.75 | 7433.00 | 7431.75 | 7431.75 | 265 |  |
| 09:18 | 7432.00 | 7433.25 | 7432.00 | 7433.00 | 491 |  |
| 09:19 | 7432.75 | 7433.00 | 7432.25 | 7433.00 | 373 |  |
| 09:20 | 7432.75 | 7434.75 | 7432.75 | 7434.00 | 951 |  |
| 09:21 | 7434.00 | 7434.75 | 7433.50 | 7434.75 | 747 |  |
| 09:22 | 7434.75 | 7435.00 | 7432.50 | 7432.75 | 1190 |  |
| 09:23 | 7432.50 | 7433.50 | 7432.25 | 7433.25 | 412 |  |
| 09:24 | 7433.00 | 7433.75 | 7432.50 | 7433.75 | 424 |  |
| 09:25 | 7433.75 | 7434.75 | 7432.50 | 7432.50 | 1100 |  |
| 09:26 | 7432.50 | 7433.00 | 7432.00 | 7433.00 | 587 |  |
| 09:27 | 7432.75 | 7433.00 | 7431.00 | 7432.25 | 1045 |  |
| 09:28 | 7432.25 | 7432.25 | 7429.75 | 7430.75 | 1588 |  |
| 09:29 | 7430.75 | 7430.75 | 7428.50 | 7429.25 | 2649 |  |
| 09:30 | 7429.25 | 7429.50 | 7421.50 | 7423.00 | 13855 | SIGNAL |
| 09:31 | 7423.00 | 7423.25 | 7417.50 | 7418.25 | 6722 | IN 7422.25 · OUT 7419.50 |
| 09:32 | 7418.00 | 7420.25 | 7416.75 | 7416.75 | 7098 |  |
| 09:33 | 7416.75 | 7421.00 | 7416.75 | 7420.75 | 5016 |  |
| 09:34 | 7420.75 | 7421.25 | 7419.00 | 7420.25 | 2999 |  |
| 09:35 | 7420.50 | 7420.50 | 7415.75 | 7415.75 | 5000 |  |
| 09:36 | 7415.75 | 7416.25 | 7412.75 | 7412.75 | 6137 |  |
| 09:37 | 7412.75 | 7415.25 | 7411.75 | 7412.00 | 5011 |  |
| 09:38 | 7412.00 | 7414.50 | 7411.00 | 7413.25 | 5000 |  |
| 09:39 | 7413.25 | 7414.50 | 7411.50 | 7412.00 | 3556 |  |
| 09:40 | 7412.25 | 7413.75 | 7409.50 | 7412.75 | 5705 |  |
| 09:41 | 7412.50 | 7416.50 | 7412.50 | 7415.75 | 5238 |  |
| 09:42 | 7415.75 | 7419.00 | 7413.50 | 7415.50 | 8062 |  |
| 09:43 | 7415.75 | 7417.25 | 7413.25 | 7414.25 | 4071 |  |
| 09:44 | 7414.50 | 7415.25 | 7412.50 | 7413.50 | 2861 |  |
| 09:45 | 7413.50 | 7413.50 | 7409.50 | 7410.00 | 5893 |  |
| 09:46 | 7410.00 | 7411.00 | 7406.25 | 7408.00 | 7031 |  |

</details>

## How the columns are measured

- **Signal** = the candle the setup keys on, measured on the 1-minute bar that holds it (the 5-minute candle on a trade he took off the 5-minute chart, or read off his own chart where a line says so); **stop** = beyond it (its low for a long, its high for a short).
- **Chase %** = how far the fill sat past the signal close, as a share of the signal range. 0 = filled at the close; negative = better than the close. **same bar** = the fill came inside the signal bar itself (he traded a 5- or 10-second chart), so that bar closed after the fill and chase cannot be measured from these bars.
- **R** = the result in price points divided by the risk to the stop, before fees. **P&L $** is after fees (about $1.90 a round trip on a micro), so a small positive R can still be a dollar loss; a win = P&L above $0.
- **MAE % of risk** = the worst move against him while held, divided by the risk. **MFE pts** = the best move in his favour while held, in points. **Capture %** = his result divided by MFE pts (winners and scratches only).
- **Best next 15m** = the best move, in points from his entry price, in the 15 one-minute bars after the exit (negative when price never got back to his entry). Stocks with only 5-minute bars use the three 5-minute bars after the exit bar, so theirs is approximate.
- While held means: from 10-second bars when they exist (trades from 2026-06-26 on), to the nearest 10 seconds (the 10-second bars the fill and the exit fall in are counted whole). Otherwise the bar the fill came in and the bar the exit came in are both left out, because each also holds prices from outside the trade (the exit price itself still counts). A trade that did not stay through one full bar shows —.
- **Vol × / Body ×** = the signal bar's volume and body against the average / median of the 10 bars before it.
- Futures prices are unadjusted CME front-month bars (MES is read from ES bars and MNQ from NQ bars; the micro and full-size prints can differ by a tick or two on a fast bar). 10-second bars are the NinjaTrader capture, moved back 10 seconds because it stamps each bar at its close. Stock bars are Yahoo 1- or 5-minute bars kept with the scores.
