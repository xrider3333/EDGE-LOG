# LEG SCAN - new-mechanism ideas (a SCAN, not a validate)

_Generated 2026-09-08 by `tools/leg_scan_ideas.py`. Nothing here is crowned._

Run window 2010-06-07 .. 2025-06-30. Discovery 2010-06-07 .. 2019-06-21, holdout 2019-06-22 .. 2025-06-30.

## Pre-registration (written before the first run)

```
tools/leg_scan_ideas.py - NEW-MECHANISM LEG SCAN (not a validate, nothing gets crowned).

The four existing families (ORB, NOISE, ENGU-Q, NQDIP) have been mined out: every
in-sample filter added to them dies out of sample. This file does not re-cut them.
It tests mechanisms that use a DIFFERENT trigger or DIFFERENT information - the
opening gap, scheduled event days, the NQ-vs-ES strength spread, and the last hour
of the day - against a pre-registered grid, an honest calendar split, and fixed
exits. Every cell is reported, not just the good ones.

===============================================================================
PRE-REGISTRATION  (written before the first run; unchanged after seeing results)
===============================================================================
WINDOW      2010-06-07 .. 2025-06-30.  2025-07-01 onward is a LOCKBOX: this file
            never loads a bar from it (enforced in code and in the tests).
SPLIT       DISCOVERY = the first 60% of that window by CALENDAR DATE.
            HOLDOUT   = the remaining 40%.  No re-splitting, no re-shuffling.
GRIDS       Fixed below, per mechanism. EVERY cell is reported, never only the best.
SCORE       Per cell, computed SEPARATELY on discovery and on holdout:
              n        = number of trades
              net $    = total profit/loss in dollars, after costs
              PF       = profit factor = (dollars won) / (dollars lost)
              maxDD $  = largest peak-to-trough fall of the running total, in dollars
              MAR      = (net $ / years in that segment) / maxDD $   (annualised MAR)
              trades/yr= n / years in that segment
              EV R     = average trade in R, where R = the average LOSING trade in $
LEAD BAR    A cell is a LEAD only if DISCOVERY and HOLDOUT each show
              PF >= 1.25  AND  MAR >= 1.0  AND  n >= 80.
            Anything else is NOT a lead, however pretty one half looks.
EXITS       Fixed per mechanism, never searched:
              stop  = 1.5 x the 14-bar ATR of the 5-minute chart at the entry bar,
                      unless a mechanism states its own stop (only M2a does);
              time exit as stated per mechanism;
              flat at 16:00 ET always (the 15:55 bar's close).
            Inside a bar the STOP is assumed to hit before any target (pessimistic),
            and a bar that OPENS through the stop fills at that open, not at the stop.
COSTS       0.533 NQ points round trip x $20/point = $10.66 per trade, one contract.
YEAR VIEW   (M5) Year-by-year net dollars is printed for every cell, in discovery and
            in holdout, so a cell that is really one lucky year is visible on sight.
===============================================================================

MECHANISMS
  M1 OPENING GAP    gap = the 09:30 open minus the prior day's regular-hours close,
                    divided by the prior 20 days' average daily range (ADR20).
                    (a) FADE  : |gap| >= g and the first 5-minute bar closes back
                        toward the prior close -> trade toward the gap fill at 09:35,
                        target = the prior close (a full fill), time exit 11:00.
                    (b) GO-WITH: |gap| >= g and the first bar extends the gap ->
                        trade with the gap at 09:35, time exit 12:00.
                    g in {0.3, 0.5, 0.8}. Each also split by whether the OVERNIGHT
                    session (NQ 5m ETH master, prior 18:00 -> 09:30) had already
                    traded back more than half of the gap before the open.
  M2 EVENT DAYS     (a) FOMC 2pm : the 14:00-14:30 range; if the 14:30 bar CLOSES
                        beyond it, enter that way at 14:35, stop = the range's other
                        side, hold to 15:55.
                    (b) OPEX     : third Friday; at 10:30 fade the first hour's move
                        back toward the prior close, target = prior close, exit 15:00.
                    (c) MONTH-END: buy at 09:35 on the last 2 trading days of a month,
                        exit 15:55; and separately the first 2 trading days.
                    Small samples by construction - the n is stated for each.
  M3 NQ vs ES       At 10:30, spread = NQ's first-hour % return minus ES's.
                    (a) CONTINUATION: spread >= s -> buy NQ; <= -s -> short NQ; 15:55.
                    (b) MEAN-REVERSION: the same thresholds, opposite direction.
                    s in {0.20%, 0.35%, 0.50%}. Repeated with the PRIOR FULL DAY's
                    NQ-minus-ES close-to-close return, entering at 09:35 instead.
  M4 LAST HOUR      At 15:00, close-position = where the last price sits inside the
                    day's 09:30-14:55 high-low range (1.0 = at the high, 0 = at the low).
                    >= 0.8 -> buy, <= 0.2 -> sell, exit 15:55; only on days whose range
                    is at least m x ADR20, m in {1.0, 1.5, 2.0}. Fade = same, opposite.
  M5 INFORMATION    Not a leg - the year-by-year net printed for every cell above.

OUTPUT   prints a table; writes docs/anatomy/LEG_SCAN_IDEAS.md
USAGE    python tools/leg_scan_ideas.py            (a few minutes on 5m data)
         python tools/leg_scan_ideas.py --quick    (2013-2016 only, for smoke tests)
```

## Plain-English glossary

- **Discovery / holdout** - the window is cut in two by date. Rules are
  looked at on the first 60% (discovery); the last 40% (holdout) is the
  fresh data that decides whether the idea was real.
- **Lockbox** - 2025-07 onward. Not loaded at all here, kept for later.
- **PF (profit factor)** - dollars won divided by dollars lost. Below 1.0
  the rule loses money.
- **maxDD** - the deepest peak-to-trough fall of the running total, in dollars.
- **MAR** - average dollars per year divided by maxDD: what you earn per year
  for each dollar of worst-case pain. Higher is better; 1.0 is the bar here.
- **EV R** - the average trade expressed in units of the average LOSING trade.
  0.10 means a typical trade earns a tenth of a typical loss.
- **ADR20** - the average daily high-to-low range over the prior 20 days.
- **LEAD** - discovery AND holdout both clear PF>=1.25, MAR>=1.0, n>=80.

## Verdict

**No leads.** Not one of the 40 cells cleared the pre-registered bar on discovery and holdout at the same time.

## All cells (every one, not just the good ones)

| cell | seg | n | net $ | PF | maxDD $ | MAR | tr/yr | EV R | LEAD |
|---|---|---:|---:|---:|---:|---:|---:|---:|:--:|
| M1 FADE g=0.3 all | DISC | 580 | 8151 | 1.12 | 5227 | 0.17 | 64.2 | 0.06 | - |
| M1 FADE g=0.3 all | HOLD | 416 | 6752 | 1.03 | 19816 | 0.06 | 69.1 | 0.02 |  |
| M1 FADE g=0.3 not_retraced | DISC | 110 | 6124 | 1.43 | 2246 | 0.30 | 12.2 | 0.22 | - |
| M1 FADE g=0.3 not_retraced | HOLD | 103 | 23017 | 1.46 | 7364 | 0.52 | 17.1 | 0.23 |  |
| M1 FADE g=0.3 on_retraced | DISC | 470 | 2026 | 1.04 | 7760 | 0.03 | 52.0 | 0.02 | - |
| M1 FADE g=0.3 on_retraced | HOLD | 313 | -16265 | 0.91 | 27282 | -0.10 | 52.0 | -0.05 |  |
| M1 FADE g=0.5 all | DISC | 311 | 5263 | 1.12 | 5849 | 0.10 | 34.4 | 0.07 | - |
| M1 FADE g=0.5 all | HOLD | 236 | 14284 | 1.10 | 18654 | 0.13 | 39.2 | 0.06 |  |
| M1 FADE g=0.5 not_retraced | DISC | 77 | 5721 | 1.56 | 1852 | 0.34 | 8.5 | 0.29 | - |
| M1 FADE g=0.5 not_retraced | HOLD | 65 | 21013 | 1.64 | 6212 | 0.56 | 10.8 | 0.31 |  |
| M1 FADE g=0.5 on_retraced | DISC | 234 | -457 | 0.99 | 6380 | -0.01 | 25.9 | -0.01 | - |
| M1 FADE g=0.5 on_retraced | HOLD | 171 | -6729 | 0.94 | 20787 | -0.05 | 28.4 | -0.04 |  |
| M1 FADE g=0.8 all | DISC | 128 | -1694 | 0.92 | 5408 | -0.03 | 14.2 | -0.05 | - |
| M1 FADE g=0.8 all | HOLD | 105 | 11033 | 1.15 | 14090 | 0.13 | 17.4 | 0.08 |  |
| M1 FADE g=0.8 not_retraced | DISC | 43 | 3668 | 1.63 | 1771 | 0.23 | 4.8 | 0.31 | - |
| M1 FADE g=0.8 not_retraced | HOLD | 37 | 16941 | 1.74 | 5522 | 0.51 | 6.1 | 0.38 |  |
| M1 FADE g=0.8 on_retraced | DISC | 85 | -5362 | 0.66 | 6455 | -0.09 | 9.4 | -0.22 | - |
| M1 FADE g=0.8 on_retraced | HOLD | 68 | -5908 | 0.88 | 14810 | -0.07 | 11.3 | -0.07 |  |
| M1 GOWITH g=0.3 all | DISC | 473 | 10814 | 1.16 | 8546 | 0.14 | 52.3 | 0.10 | - |
| M1 GOWITH g=0.3 all | HOLD | 344 | 56799 | 1.27 | 24021 | 0.39 | 57.1 | 0.16 |  |
| M1 GOWITH g=0.3 not_retraced | DISC | 81 | 91 | 1.01 | 2875 | 0.00 | 9.0 | 0.00 | - |
| M1 GOWITH g=0.3 not_retraced | HOLD | 60 | 8532 | 1.24 | 9414 | 0.15 | 10.0 | 0.13 |  |
| M1 GOWITH g=0.3 on_retraced | DISC | 392 | 10723 | 1.19 | 7962 | 0.15 | 43.4 | 0.12 | - |
| M1 GOWITH g=0.3 on_retraced | HOLD | 284 | 48267 | 1.27 | 18768 | 0.43 | 47.2 | 0.16 |  |
| M1 GOWITH g=0.5 all | DISC | 249 | -265 | 0.99 | 8377 | -0.00 | 27.6 | -0.00 | - |
| M1 GOWITH g=0.5 all | HOLD | 203 | 32840 | 1.24 | 18106 | 0.30 | 33.7 | 0.14 |  |
| M1 GOWITH g=0.5 not_retraced | DISC | 50 | -1977 | 0.73 | 3393 | -0.06 | 5.5 | -0.18 | - |
| M1 GOWITH g=0.5 not_retraced | HOLD | 40 | 3977 | 1.16 | 6516 | 0.10 | 6.6 | 0.08 |  |
| M1 GOWITH g=0.5 on_retraced | DISC | 199 | 1712 | 1.06 | 7220 | 0.03 | 22.0 | 0.03 | - |
| M1 GOWITH g=0.5 on_retraced | HOLD | 163 | 28862 | 1.26 | 12821 | 0.37 | 27.1 | 0.15 |  |
| M1 GOWITH g=0.8 all | DISC | 86 | -417 | 0.97 | 5787 | -0.01 | 9.5 | -0.02 | - |
| M1 GOWITH g=0.8 all | HOLD | 69 | 5862 | 1.11 | 11454 | 0.08 | 11.5 | 0.06 |  |
| M1 GOWITH g=0.8 not_retraced | DISC | 22 | -1309 | 0.55 | 1309 | -0.11 | 2.4 | -0.29 | - |
| M1 GOWITH g=0.8 not_retraced | HOLD | 13 | -10205 | 0.35 | 14673 | -0.12 | 2.2 | -0.45 |  |
| M1 GOWITH g=0.8 on_retraced | DISC | 64 | 892 | 1.09 | 5362 | 0.02 | 7.1 | 0.05 | - |
| M1 GOWITH g=0.8 on_retraced | HOLD | 56 | 16066 | 1.40 | 8135 | 0.33 | 9.3 | 0.21 |  |
| M2a FOMC 14:30 break | DISC | 9 | 89 | 1.07 | 727 | 0.01 | 1.0 | 0.04 | - |
| M2a FOMC 14:30 break | HOLD | 10 | -13022 | 0.17 | 14748 | -0.15 | 1.7 | -0.58 |  |
| M2b OPEX fade 1st hour | DISC | 106 | -9747 | 0.51 | 12216 | -0.09 | 11.7 | -0.34 | - |
| M2b OPEX fade 1st hour | HOLD | 70 | -45578 | 0.28 | 45578 | -0.17 | 11.6 | -0.52 |  |
| M2c MONTH-END last2 long | DISC | 216 | -8947 | 0.74 | 9247 | -0.11 | 23.9 | -0.20 | - |
| M2c MONTH-END last2 long | HOLD | 146 | 445 | 1.00 | 22623 | 0.00 | 24.2 | 0.00 |  |
| M2c MONTH-START first2 long | DISC | 217 | 4702 | 1.13 | 7120 | 0.07 | 24.0 | 0.10 | - |
| M2c MONTH-START first2 long | HOLD | 144 | 46319 | 1.53 | 9171 | 0.84 | 23.9 | 0.34 |  |
| M3a 1sthr CONT s=0.20 | DISC | 835 | 49110 | 1.34 | 10795 | 0.50 | 92.4 | 0.21 | - |
| M3a 1sthr CONT s=0.20 | HOLD | 756 | 97081 | 1.17 | 41717 | 0.39 | 125.5 | 0.10 |  |
| M3a 1sthr CONT s=0.35 | DISC | 317 | 30874 | 1.47 | 8342 | 0.41 | 35.1 | 0.28 | - |
| M3a 1sthr CONT s=0.35 | HOLD | 369 | 71531 | 1.25 | 27834 | 0.43 | 61.3 | 0.14 |  |
| M3a 1sthr CONT s=0.50 | DISC | 124 | 9355 | 1.31 | 5613 | 0.18 | 13.7 | 0.19 | - |
| M3a 1sthr CONT s=0.50 | HOLD | 190 | 35242 | 1.22 | 35407 | 0.17 | 31.5 | 0.12 |  |
| M3b 1sthr REV  s=0.20 | DISC | 835 | -32577 | 0.81 | 33167 | -0.11 | 92.4 | -0.13 | - |
| M3b 1sthr REV  s=0.20 | HOLD | 756 | -38389 | 0.94 | 72521 | -0.09 | 125.5 | -0.04 |  |
| M3b 1sthr REV  s=0.35 | DISC | 317 | -15458 | 0.80 | 15777 | -0.11 | 35.1 | -0.14 | - |
| M3b 1sthr REV  s=0.35 | HOLD | 369 | -34523 | 0.90 | 62249 | -0.09 | 61.3 | -0.07 |  |
| M3b 1sthr REV  s=0.50 | DISC | 124 | -14235 | 0.63 | 14765 | -0.11 | 13.7 | -0.27 | - |
| M3b 1sthr REV  s=0.50 | HOLD | 190 | -28159 | 0.85 | 34219 | -0.14 | 31.5 | -0.10 |  |
| M3c prevday CONT s=0.20 | DISC | 1305 | -3760 | 0.98 | 28242 | -0.01 | 144.4 | -0.01 | - |
| M3c prevday CONT s=0.20 | HOLD | 1036 | 81800 | 1.11 | 63754 | 0.21 | 172.0 | 0.08 |  |
| M3c prevday CONT s=0.35 | DISC | 778 | -13197 | 0.91 | 19160 | -0.08 | 86.1 | -0.07 | - |
| M3c prevday CONT s=0.35 | HOLD | 721 | 47700 | 1.09 | 50985 | 0.16 | 119.7 | 0.07 |  |
| M3c prevday CONT s=0.50 | DISC | 434 | -3261 | 0.96 | 16031 | -0.02 | 48.0 | -0.03 | - |
| M3c prevday CONT s=0.50 | HOLD | 507 | 33099 | 1.08 | 47281 | 0.12 | 84.2 | 0.06 |  |
| M3d prevday REV  s=0.20 | DISC | 1305 | 18804 | 1.09 | 14218 | 0.15 | 144.4 | 0.06 | - |
| M3d prevday REV  s=0.20 | HOLD | 1036 | 55002 | 1.08 | 48909 | 0.19 | 172.0 | 0.06 |  |
| M3d prevday REV  s=0.35 | DISC | 778 | 192 | 1.00 | 19784 | 0.00 | 86.1 | 0.00 | - |
| M3d prevday REV  s=0.35 | HOLD | 721 | -18688 | 0.97 | 67998 | -0.05 | 119.7 | -0.03 |  |
| M3d prevday REV  s=0.50 | DISC | 434 | -10553 | 0.88 | 18888 | -0.06 | 48.0 | -0.09 | - |
| M3d prevday REV  s=0.50 | HOLD | 507 | -3401 | 0.99 | 47649 | -0.01 | 84.2 | -0.01 |  |
| M4a LASTHR WITH rng>=1.0ADR | DISC | 483 | 15268 | 1.35 | 6574 | 0.26 | 53.4 | 0.21 | - |
| M4a LASTHR WITH rng>=1.0ADR | HOLD | 343 | 51760 | 1.41 | 11735 | 0.73 | 56.9 | 0.24 |  |
| M4a LASTHR WITH rng>=1.5ADR | DISC | 164 | 14109 | 1.90 | 1748 | 0.89 | 18.1 | 0.50 | - |
| M4a LASTHR WITH rng>=1.5ADR | HOLD | 103 | 28713 | 1.66 | 6532 | 0.73 | 17.1 | 0.38 |  |
| M4a LASTHR WITH rng>=2.0ADR | DISC | 47 | 7800 | 2.29 | 1457 | 0.59 | 5.2 | 0.77 | - |
| M4a LASTHR WITH rng>=2.0ADR | HOLD | 29 | 30207 | 4.02 | 2991 | 1.68 | 4.8 | 1.35 |  |
| M4b LASTHR FADE rng>=1.0ADR | DISC | 483 | -21835 | 0.59 | 21914 | -0.11 | 53.4 | -0.27 | - |
| M4b LASTHR FADE rng>=1.0ADR | HOLD | 343 | -40964 | 0.75 | 42061 | -0.16 | 56.9 | -0.17 |  |
| M4b LASTHR FADE rng>=1.5ADR | DISC | 164 | -12355 | 0.50 | 12355 | -0.11 | 18.1 | -0.35 | - |
| M4b LASTHR FADE rng>=1.5ADR | HOLD | 103 | -17373 | 0.72 | 18520 | -0.16 | 17.1 | -0.19 |  |
| M4b LASTHR FADE rng>=2.0ADR | DISC | 47 | -4534 | 0.48 | 4911 | -0.10 | 5.2 | -0.36 | - |
| M4b LASTHR FADE rng>=2.0ADR | HOLD | 29 | -8271 | 0.64 | 9829 | -0.14 | 4.8 | -0.26 |  |

## M5 - year-by-year net dollars, every cell

One lucky year is the commonest way a scan fools itself; D = a discovery
year, H = a holdout year.

- **M1 FADE g=0.3 all** - 2010D +1697  2011D +1186  2012D -154  2013D +1775  2014D +3800  2015D -1191  2016D -2078  2017D +1460  2018D +14  2019D +1642  2019H +129  2020H +6164  2021H -2959  2022H +3491  2023H +4895  2024H -345  2025H -4623
- **M1 FADE g=0.3 not_retraced** - 2010D -120  2011D +817  2012D -347  2013D -286  2014D +1457  2015D +1900  2016D -1496  2017D +1989  2018D +1654  2019D +556  2019H +1183  2020H +1022  2021H +1982  2022H +8582  2023H -2380  2024H +7448  2025H +5179
- **M1 FADE g=0.3 on_retraced** - 2010D +1817  2011D +368  2012D +194  2013D +2061  2014D +2343  2015D -3091  2016D -582  2017D -529  2018D -1640  2019D +1086  2019H -1055  2020H +5142  2021H -4941  2022H -5091  2023H +7276  2024H -7793  2025H -9803
- **M1 FADE g=0.5 all** - 2010D +1241  2011D +137  2012D -665  2013D +1294  2014D +2787  2015D +530  2016D -2050  2017D -580  2018D -600  2019D +3170  2019H +533  2020H +6002  2021H -7376  2022H +3550  2023H +4491  2024H +3838  2025H +3246
- **M1 FADE g=0.5 not_retraced** - 2011D +640  2012D -616  2013D +250  2014D +1292  2015D +1777  2016D -1354  2017D +977  2018D +1023  2019D +1732  2019H +1462  2020H -269  2021H -3053  2022H +7341  2023H -388  2024H +10058  2025H +5863
- **M1 FADE g=0.5 on_retraced** - 2010D +1241  2011D -503  2012D -49  2013D +1045  2014D +1495  2015D -1247  2016D -696  2017D -1557  2018D -1623  2019D +1438  2019H -929  2020H +6271  2021H -4323  2022H -3790  2023H +4879  2024H -6221  2025H -2617
- **M1 FADE g=0.8 all** - 2010D +400  2011D -285  2012D -1137  2013D +551  2014D +2911  2015D -19  2016D -2193  2017D -488  2018D -683  2019D -750  2019H +188  2020H +7274  2021H -5091  2022H +2401  2023H +1118  2024H +3895  2025H +1249
- **M1 FADE g=0.8 not_retraced** - 2011D +504  2012D -48  2013D +344  2014D +1083  2015D +830  2016D -1310  2017D +489  2018D -191  2019D +1967  2019H +494  2020H +1923  2021H -2154  2022H +5979  2023H -1553  2024H +6452  2025H +5799
- **M1 FADE g=0.8 on_retraced** - 2010D +400  2011D -789  2012D -1089  2013D +207  2014D +1828  2015D -850  2016D -883  2017D -977  2018D -492  2019D -2716  2019H -307  2020H +5351  2021H -2937  2022H -3578  2023H +2671  2024H -2557  2025H -4551
- **M1 GOWITH g=0.3 all** - 2010D +781  2011D +1367  2012D -742  2013D +1920  2014D +2200  2015D +6  2016D +1217  2017D +758  2018D +5087  2019D -1780  2019H +3801  2020H +2504  2021H +920  2022H +27290  2023H +124  2024H +33630  2025H -11471
- **M1 GOWITH g=0.3 not_retraced** - 2010D -144  2011D +579  2012D -422  2013D +56  2014D -103  2015D +1412  2016D +816  2017D +94  2018D -848  2019D -1349  2019H +2180  2020H -315  2021H -4038  2022H +2537  2023H +3486  2024H +6699  2025H -2016
- **M1 GOWITH g=0.3 on_retraced** - 2010D +924  2011D +788  2012D -320  2013D +1864  2014D +2303  2015D -1406  2016D +401  2017D +664  2018D +5935  2019D -430  2019H +1622  2020H +2820  2021H +4958  2022H +24753  2023H -3362  2024H +26931  2025H -9455
- **M1 GOWITH g=0.5 all** - 2010D +1715  2011D +701  2012D +177  2013D +1619  2014D +110  2015D -1565  2016D +888  2017D -616  2018D -1304  2019D -1989  2019H +2878  2020H -6718  2021H -548  2022H +24819  2023H +20  2024H +22426  2025H -10037
- **M1 GOWITH g=0.5 not_retraced** - 2010D -168  2011D +42  2012D +70  2013D -86  2014D -103  2015D +852  2016D +358  2017D +117  2018D -2365  2019D -694  2019H +2570  2020H -223  2021H -135  2022H -2371  2023H +2584  2024H +670  2025H +882
- **M1 GOWITH g=0.5 on_retraced** - 2010D +1883  2011D +659  2012D +107  2013D +1705  2014D +212  2015D -2417  2016D +530  2017D -734  2018D +1061  2019D -1295  2019H +308  2020H -6495  2021H -413  2022H +27190  2023H -2565  2024H +21756  2025H -10919
- **M1 GOWITH g=0.8 all** - 2010D +1553  2011D +515  2012D -76  2013D +556  2014D +951  2015D -879  2016D +297  2017D -362  2018D -1541  2019D -1432  2019H +1487  2020H -4524  2021H +3098  2022H +5213  2023H -2403  2024H +10318  2025H -7328
- **M1 GOWITH g=0.8 not_retraced** - 2010D -352  2011D +43  2012D -311  2013D +79  2014D -342  2016D +399  2017D +95  2018D -919  2019H +1149  2020H -5071  2021H -1858  2023H -270  2024H -2789  2025H -1365
- **M1 GOWITH g=0.8 on_retraced** - 2010D +1905  2011D +471  2012D +236  2013D +477  2014D +1294  2015D -879  2016D -102  2017D -457  2018D -622  2019D -1432  2019H +338  2020H +547  2021H +4956  2022H +5213  2023H -2133  2024H +13108  2025H -5963
- **M2a FOMC 14:30 break** - 2010D -727  2011D +489  2013D -221  2015D +548  2020H -856  2021H +1064  2022H -12937  2023H -711  2024H -91  2025H +509
- **M2b OPEX fade 1st hour** - 2010D -399  2011D +1421  2012D -1650  2013D -1163  2014D -475  2015D -3766  2016D -2493  2017D -1412  2018D +2297  2019D -2105  2019H -2955  2020H -3306  2021H -5778  2022H -874  2023H -8126  2024H -8932  2025H -15607
- **M2c MONTH-END last2 long** - 2010D -1843  2011D -944  2012D +203  2013D +1866  2014D -556  2015D -2311  2016D -1684  2017D +544  2018D -2438  2019D -1784  2019H -1270  2020H -5833  2021H +5119  2022H +1884  2023H +2502  2024H -12787  2025H +10830
- **M2c MONTH-START first2 long** - 2010D -35  2011D -1035  2012D +170  2013D -1534  2014D -593  2015D +1502  2016D +2488  2017D -1859  2018D +4241  2019D +1358  2019H -3188  2020H +11124  2021H +5522  2022H +10812  2023H +8611  2024H +815  2025H +12623
- **M3a 1sthr CONT s=0.20** - 2010D -2484  2011D +5981  2012D +2054  2013D +1186  2014D -1137  2015D -840  2016D -1767  2017D +6663  2018D +35454  2019D +3999  2019H -373  2020H -14356  2021H -3748  2022H +39118  2023H +29385  2024H +38799  2025H +8256
- **M3a 1sthr CONT s=0.35** - 2010D -105  2011D +3070  2012D +772  2013D +286  2014D +1139  2015D -1340  2016D -3146  2017D +876  2018D +24519  2019D +4803  2019H -2051  2020H -17873  2021H +23660  2022H +43806  2023H +8032  2024H +10011  2025H +5947
- **M3a 1sthr CONT s=0.50** - 2010D +1  2011D -21  2012D -1030  2013D -167  2014D +1031  2015D -2717  2016D -9  2017D +1532  2018D +4546  2019D +6191  2019H -1559  2020H -25415  2021H +17755  2022H +38354  2023H -6259  2024H +1826  2025H +10541
- **M3b 1sthr REV  s=0.20** - 2010D -470  2011D -6961  2012D -5901  2013D -2953  2014D -3007  2015D +1946  2016D -1029  2017D -2657  2018D -3737  2019D -7809  2019H -1098  2020H -4317  2021H -5896  2022H +13951  2023H -28648  2024H -26382  2025H +14002
- **M3b 1sthr REV  s=0.35** - 2010D -796  2011D -5848  2012D -1310  2013D -954  2014D -2447  2015D +1241  2016D +613  2017D -1635  2018D -1178  2019D -3145  2019H +329  2020H +682  2021H -21079  2022H +1581  2023H -17221  2024H -16690  2025H +17875
- **M3b 1sthr REV  s=0.50** - 2010D -759  2011D -2486  2012D -492  2013D -314  2014D +1081  2015D +1835  2016D -2945  2017D -1572  2018D -3825  2019D -4758  2019H +264  2020H -3786  2021H -17344  2022H -2781  2023H +4970  2024H -3680  2025H -5801
- **M3c prevday CONT s=0.20** - 2010D -3858  2011D -1191  2012D -1691  2013D -3716  2014D -4390  2015D -5147  2016D -4277  2017D +1858  2018D +7692  2019D +10961  2019H -1320  2020H -47823  2021H +54993  2022H +42396  2023H +53484  2024H +1239  2025H -21169
- **M3c prevday CONT s=0.35** - 2010D -3646  2011D +677  2012D -1539  2013D -2428  2014D -1727  2015D -4430  2016D -1789  2017D -3078  2018D +3994  2019D +769  2019H +904  2020H -35383  2021H +35896  2022H +14914  2023H +41958  2024H -5498  2025H -5091
- **M3c prevday CONT s=0.50** - 2010D -1781  2011D -821  2012D -1299  2013D -2128  2014D -422  2015D -4760  2016D -792  2017D -1058  2018D +7179  2019D +2621  2019H -1425  2020H -31045  2021H +28732  2022H +11314  2023H +35214  2024H -11372  2025H +1680
- **M3d prevday REV  s=0.20** - 2010D -3970  2011D -2357  2012D +10916  2013D -1502  2014D +6998  2015D +4554  2016D -3739  2017D -1333  2018D +6319  2019D +2918  2019H +2937  2020H +10409  2021H +3101  2022H +16028  2023H -17375  2024H -8849  2025H +48752
- **M3d prevday REV  s=0.35** - 2010D -1360  2011D -3063  2012D +4485  2013D -1435  2014D +6373  2015D +2463  2016D -10187  2017D -2993  2018D +2697  2019D +3212  2019H -948  2020H +22757  2021H +6260  2022H -1858  2023H -10620  2024H -28572  2025H -5707
- **M3d prevday REV  s=0.50** - 2010D -1077  2011D -1096  2012D +3772  2013D -94  2014D +2884  2015D +84  2016D -5218  2017D -3934  2018D -6322  2019D +449  2019H -1821  2020H +402  2021H +11939  2022H +1532  2023H -16099  2024H -14124  2025H +14769
- **M4a LASTHR WITH rng>=1.0ADR** - 2010D +113  2011D -2707  2012D -380  2013D +353  2014D -230  2015D +34  2016D +538  2017D +167  2018D +20315  2019D -2936  2019H +31  2020H +559  2021H +12523  2022H +28441  2023H +6783  2024H -5778  2025H +9201
- **M4a LASTHR WITH rng>=1.5ADR** - 2010D +14  2011D -643  2012D -100  2013D +1755  2014D -219  2015D +457  2016D +950  2017D +970  2018D +11921  2019D -997  2019H -438  2020H -75  2021H -2562  2022H +11663  2023H +1637  2024H +3648  2025H +14840
- **M4a LASTHR WITH rng>=2.0ADR** - 2011D -770  2012D -250  2013D +652  2014D -704  2015D +527  2016D +391  2017D +1006  2018D +7656  2019D -709  2019H +247  2020H -203  2021H -840  2022H +4753  2023H -1805  2024H +9667  2025H +18388
- **M4b LASTHR FADE rng>=1.0ADR** - 2010D -1250  2011D -1398  2012D -381  2013D -140  2014D -1252  2015D -1920  2016D -525  2017D -2453  2018D -11770  2019D -745  2019H +66  2020H -5693  2021H -3654  2022H -14521  2023H -12838  2024H +3792  2025H -8116
- **M4b LASTHR FADE rng>=1.5ADR** - 2010D -36  2011D -728  2012D -811  2013D -865  2014D -843  2015D -930  2016D -500  2017D -857  2018D -5464  2019D -1323  2019H +417  2020H -5483  2021H +2602  2022H -3241  2023H -4777  2024H +4028  2025H -10919
- **M4b LASTHR FADE rng>=2.0ADR** - 2011D +56  2012D -205  2013D -674  2014D +221  2015D -787  2016D -261  2017D -1132  2018D -1382  2019D -371  2019H -248  2020H -4644  2021H +5298  2022H -1757  2023H +1176  2024H +966  2025H -9062

## Closest misses

"best year" = the share of that half's net dollars that came from its
single best calendar year. A high share means the cell is one good year
wearing a fifteen-year costume.

- **M4a LASTHR WITH rng>=1.5ADR** - discovery PF 1.90 / MAR 0.89 / n 164 / net 14109 (best year 84% from 2018); holdout PF 1.66 / MAR 0.73 / n 103 / net 28713 (best year 52% from 2025).
- **M4a LASTHR WITH rng>=1.0ADR** - discovery PF 1.35 / MAR 0.26 / n 483 / net 15268 (best year 133% from 2018); holdout PF 1.41 / MAR 0.73 / n 343 / net 51760 (best year 55% from 2022).
- **M3a 1sthr CONT s=0.35** - discovery PF 1.47 / MAR 0.41 / n 317 / net 30874 (best year 79% from 2018); holdout PF 1.25 / MAR 0.43 / n 369 / net 71531 (best year 61% from 2022).
- **M1 FADE g=0.3 not_retraced** - discovery PF 1.43 / MAR 0.30 / n 110 / net 6124 (best year 32% from 2017); holdout PF 1.46 / MAR 0.52 / n 103 / net 23017 (best year 37% from 2022).
- **M3a 1sthr CONT s=0.20** - discovery PF 1.34 / MAR 0.50 / n 835 / net 49110 (best year 72% from 2018); holdout PF 1.17 / MAR 0.39 / n 756 / net 97081 (best year 40% from 2022).
- **M2c MONTH-START first2 long** - discovery PF 1.13 / MAR 0.07 / n 217 / net 4702 (best year 90% from 2018); holdout PF 1.53 / MAR 0.84 / n 144 / net 46319 (best year 27% from 2025).
- **M1 FADE g=0.5 not_retraced** - discovery PF 1.56 / MAR 0.34 / n 77 / net 5721 (best year 31% from 2015); holdout PF 1.64 / MAR 0.56 / n 65 / net 21013 (best year 48% from 2024).
- **M4a LASTHR WITH rng>=2.0ADR** - discovery PF 2.29 / MAR 0.59 / n 47 / net 7800 (best year 98% from 2018); holdout PF 4.02 / MAR 1.68 / n 29 / net 30207 (best year 61% from 2025).

## Blunt summary

- 18 of 40 cells made money in BOTH halves; 11 in neither.
- Nothing here is tradeable as written. None of these mechanisms survived
  its own holdout at the bar that was set before looking.
- Costs are $10.66 a round trip, one contract. Several cells are profitable
  before costs and negative after; that is the whole story for the thin ones.
- The event cells (FOMC, OPEX, month turn) have small samples by
  construction and mostly cannot reach n>=80 in both halves; their numbers
  are reported for information, not as candidates.
