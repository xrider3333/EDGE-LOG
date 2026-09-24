# Setup journals — real discretionary trades

> One page per setup label. Each lists every real trade tagged with it in EDGE LOG (TRADING LOG ▸ TRADES), the chart links saved with it, and the OHLC behind it.

| Setup | Meaning | Futures trades | Futures wins | Futures net $ | Stock trades | Stock net $ | Older sheet-only stock trades | Page |
|---|---|---|---|---|---|---|---|---|
| CBU | Consolidation Breakout Up | 12 | 7 | 53.49 | 12 | -133.56 | 18 | [CBU.md](CBU.md) |
| ENGU | Engulfing Up | 17 | 12 | 107.25 | 1 | 3.60 | 5 | [ENGU.md](ENGU.md) |
| EBU | Breakout Up (rule not written down yet) | 9 | 4 | 29.15 | 0 | — | 4 | [EBU.md](EBU.md) |
| CBD | Consolidation Breakout Down | 4 | 3 | 21.15 | 0 | — | 0 | [CBD.md](CBD.md) |
| ENGD | Engulfing Down | 2 | 1 | -7.55 | 0 | — | 0 | [ENGD.md](ENGD.md) |

## Real trades with no setup label yet

- 2026-04-21 09:52 MES SHORT 7165.25→7165.00 (-$0.65): the sheet calls it a fat-finger order, so it is left out of every setup page. Its chart (taSMzocP) draws the long he meant; the CBU page links it on the 04-21 long.
- 2026-07-15 08:30 MNQ LONG 29932.50→29937.75 (+$8.62), 2026-07-17 11:36 MES LONG 7515.25→7516.25 (+$3.12), 2026-07-20 15:29 MES LONG 7490.00→7493.75 (+$16.87), 2026-07-27 12:25 MES LONG 7448.50→7449.00 (+$0.62), 2026-07-29 14:02 MES LONG 7445.00→7445.25 (-$0.63): no setup label and no chart in EL or the sheet. Tag them in TRADING LOG ▸ TRADES and they will be filed on the next rebuild.
- 2026-09-24 12:20 MNQ LONG 30687.00→30700.00: in the NinjaTrader fill log but not in EL yet when this was built.
- Stock trades with no label in EL or the sheet: TNMG 2026-06-29, CELZ 06-30, LHAI 07-01, LGCL 07-02, AMC 07-20, VEEA 09-15 (two trades).
- Stock trades with no label in EL but a label in the sheet (DRCT, GXAI x3, IVF, XWEL, PRSO, ATPC as CBU; ALUR and SPY x3 as EBU) are older than any free minute data. They are listed at the bottom of the CBU and EBU pages with the numbers the sheet kept.

## Where EL and the TRADETRACKER sheet disagree

- **2026-04-07, the two MES trades:** EL put each trade's label, grade, note and chart on the other fill. The 10:29 trade (6604.75→6605) is ENGU, grade A, 'questionable SL management', chart Wpfg3yIj; the 13:35 trade (6634→6637.75) is CBU, grade A+, 'should have moved SL at 1:1', chart 1cjZL1U1. Both snapshots and both sheet rows agree. Swap those four fields on the two rows in TRADING LOG ▸ TRADES.
- **2026-05-13 MES ENGD:** its chart (tOU5oaTk) is the 2026-05-07 ENGD short, saved 05-07 15:34. No chart of the 05-13 trade exists.
- **2026-06-30 MNQ CBU:** EL saved the SUGP stock chart (ABdqp2x0) on it. The sheet row’s chart (iPNDckYb) is the real one, and the page uses it.
- **2026-04-21 MES CBU (sheet row):** the sheet reuses the 2026-04-15 15:50 chart (ihNLObLD) on this row. The chart saved on the fat-finger short that minute (taSMzocP) shows the long he meant.
- **Labels that differ between EL and the sheet:** 2026-05-18 and 2026-05-19 (EL ENGU, sheet ENGD on a long), 2026-05-21 13:10 (EL EBU with a CHoS (change of structure) tag, sheet ENGU), 2026-06-30 MNQ (EL CBU, sheet EBU). The pages follow EL.
- **Notes that differ:** on 2026-04-10 EL has 09:36 "DECENT", 12:13 "MID", 15:50 "NOT BEST VOLUME"; the sheet has 09:36 "NOT BEST VOLUME", 12:13 "DECENT", 15:50 "DECENT". The 09:36 chart shows light volume, which fits the sheet, so EL’s three notes look shuffled like the 04-07 swap: check them in TRADING LOG ▸ TRADES. Also 05-15 (EL "Good Managment", sheet "DECENT") and 05-19 (EL "SL moved incorrectly", sheet "HOLD MORE"). The pages show EL’s note, or the sheet’s marked (sheet) when EL has none.
- **13 April-May trades have a label only in the sheet** (EL blank): 04-14 ×2, 04-15 ×2, 04-21 long, 04-27, 04-28, 04-29, 05-01, 05-04, 05-06, 05-07, 05-08. Their chart links also come from the sheet.
- **Extra charts in the sheet’s TRADES TO ADD tab:** XHG 2026-08-13 (EcA2vfXN) and IPST 2026-08-17 (FoDpAoxL), both saved the same day. Both were read; the IPST one moved its breakout candle to the 1-minute 10:59 candle (stop 7.86).

## Notes

- Every trade with a chart was read twice: once to place the fill, the signal candle and the stop on the bars and on the saved chart, then by a second, independent check told to disprove the first. 5 trades had a disputed field, and a third check re-read the files and decided each: 2026-04-07 10:29 ENGU (which sheet row the chart backs), 2026-04-21 fat-finger short (whose chart it is), 2026-05-01 EBU and 2026-05-08 MNQ CBU (the drawn stop; the second check was right both times), 2026-06-30 MNQ CBU (its 10-second stamps; the fill log settles it).
- The NinjaTrader 10-second price files are stamped at each bar’s close (EDGE LOG’s own tools shift them the same way when they read them). These pages shift them back 10 seconds, so every time shown is the start of the bar.
- Trades bought inside the signal minute (off a 5- or 10-second chart) show "same bar" for chase: the 1-minute candle closed after the fill, so they are left out of the chase and volume findings.
- The end-of-day SCORE has no score for seven July-August futures trades (07-10, 07-15, 07-17, 07-20, 07-27, 07-29, 08-04: "no 1-minute data"); the NinjaTrader 10-second capture covers those days, and these pages use it.
- Six stock trades (SUGP, GMM, XHG, IPST, SLE, HOWL) only have the 5-minute bars kept with their scores, so their breakout candle was read off the 1-minute or 10-second chart he saved. LABT’s was read off its 10-second chart too, since 1-minute bars cannot show a 10-second candle. Each page says so.
- Seven stock readings here differ from the SCORE in TRADING LOG, which used 5-minute bars or another candle: EHGO (09:29, not 09:31), LABT (the 10-second 08:08:00 candle), SUGP, GMM, XHG, IPST and HOWL. The SCORE has not been re-run on them.
