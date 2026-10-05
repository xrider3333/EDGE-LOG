# PRE-REGISTRATION - BONDLEAD r1: does the bond market's morning tell NQ's afternoon? (new type 3 of 3, MANAGER #40)

Drafted 2026-10-05 by the NOISE lane BEFORE any real-direction number exists.
- Computed so far: the power line below (from a coin-flip leg) and trade COUNTS at candidate thresholds, used to set
  z0 (see Rules). Neither involves a direction.
- Harness: `tools/bondlead_r1_stageA.py` (only `--power` has run). It reuses the HALFHOUR r1 book and stats code.

## Mechanism (theory and literature)
Macro news (rates, inflation, growth) is priced first and most fully in the Treasury market. Many equity investors pay
limited attention to other asset classes, so they fold that news into stock prices over hours, not minutes.
- Hong, Torous & Valkanov (2007, Journal of Financial Economics): information diffuses gradually across markets.
- Pitkajarvi, Suominen & Vaittinen (2020, Journal of Financial Economics): past bond returns predict equity returns
  ("cross-asset signals").

The intraday version: the part of NQ's morning move that the bond market's morning move explains should keep going in
the afternoon.

The stock-bond link changes sign. In 2022 stocks and bonds fell together; in other years bonds rose when stocks fell.
So the rule never assumes a sign: it re-estimates the link every day from the previous 60 sessions.

## What is different (one line), and the dead families it is not
**Every dead intraday family on EL reads equity prices only, NQ's or ES's. This one reads the Treasury market's
same-day move and trades only the part of NQ that the bond market explains, against a twin that trades NQ's own
morning move.**

Dead and not re-tested:
- Last-hour momentum (2.5).
- NQ-vs-ES relative value (2.24, 2.45).
- Breadth (2.48).
- Gap and event families (2.5, 2.6).
- Overnight and European-morning drift (2.13, 2.15).
- Crash-regime short (2.16).
- Transferring ORB, NOISE and TTM onto the funds (2.40 / 2.49): that traded the funds; this trades NQ.
- Every NOISE re-size in rounds 63-70 (pyramid, checkpoints, delta, time stop, ES confirmation, overnight clearance,
  breakeven, tilt depth, short tilt).

## Rules (frozen)
**Data.**
- NQ 5m RTH no-adjust master (id 37).
- IEF and GLD 5m RTH masters (Alpaca split-adjusted, the TRANSFER r2 pull, from 2016-01-04).
- Every master is loaded with date_to 2025-06-29.
- Trades are counted in 2016-07-01 .. 2025-06-29. The 60-session warm-up ends in April 2016.
- NQ sessions without a 15:55 bar are dropped. IEF is missing on 2 of 2,240 walk-forward days; those days have no trade.

**Morning return.** For NQ and each fund: from the first open at or after 09:30 (within the first three bars) to the
last close at or before the window end (within the last three bars), in percent.

**Signal.**
- Fit an OLS of NQ's morning return on the fund morning return(s) over the previous 60 sessions.
- Fitted move = slope x today's fund morning return.
- z = fitted move / SD of NQ's morning return over the same 60 sessions.

**Trade.**
- If |z| >= z0, trade 1 NQ in the sign of the fitted move.
- In at the window-end bar's open, out at the 15:55 bar's close.
- No stop. $20 a point, 0.533 point per round trip.

**z0 is on NQ's own scale.** Trade when the bond-implied move is at least a tenth of NQ's typical morning. The first
setting (0.5) gave 22 trades a year, under the map's 50, because the bond-explained part of NQ's morning is small. z0
was re-set from trade counts alone, before any direction was computed:
- primary: about 141 a year;
- 0.2: 90 a year;
- 11:00 window: 139 a year;
- IEF+GLD: 167 a year.

**Cells (4).**
- IEF, window 09:30-12:00, z0 0.1 = PRIMARY.
- IEF 12:00 z0 0.2.
- IEF 09:30-11:00 z0 0.1.
- IEF + GLD 12:00 z0 0.1.

**Twin (A5).** NQ's OWN morning move in the same seat: the sign of NQ's morning return, traded when |r / SD| >= z0. The
bond part must add something beyond plain intraday continuation.

**Family null.**
- The fund morning returns PERMUTED across days, 200 draws, seed 20261005. The slope is re-estimated on the permuted
  series.
- This keeps NQ's afternoons and the trade density, and removes only the same-day bond link.
- Statistic: the family MAX of own ROC@$30k.

## Where it sits on the MDL map (docs/MDL_MAP_R1.md)
This is the one draft of the three aimed at the map's main hunt, earning while #463 falls. Two of #463's drawdown
stretches were rates-driven (2022, and spring 2025).

The 2020 crash cuts the other way: bonds rallied while NQ fell, and a 60-session slope fitted in calm months points the
wrong way at first.

Reported, not barred: the leg's dollars in:
- 2020-03-02 .. 03-27;
- calendar 2022;
- 2025-02-19 .. 04-30;

each beside #463's own dollars in the same stretch.

## POWER LINE (written before any real-direction run; house rule MANAGER #37)
- Method: coin-flip directions on the primary's schedule (1,265 walk-forward trades, 141 a year), scaled to a $30k own
  drawdown (0.76 NQ held about four hours), added to #463's walk-forward daily. Paired stationary bootstrap, mean block
  20, 1,000 draws.
- SD of the book-add ROC@$30k lead: 17.3 points.
- MINIMUM DETECTABLE lead: 28.4 points. Four times in five: 42.9.
- **In plain words:** few, long, large trades make the book-add lead so noisy that only a very strong leg can clear the
  bootstrap. That means about $45k+ a year at a $30k own drawdown, three times the map's $15k. So A4 is close to
  unpassable here.
- The informative reads are A1, A2, A3 and A5. See the question to MANAGER below.

## Stage A bars (walk-forward only; all five must pass)
- **A1 own:**
  - primary own ROC@$30k >= 15;
  - PF > 1;
  - >= 100 trades and >= 50 a year;
  - >= 6 of the 9 July-June years positive.
- **A2 null:** primary own ROC@$30k above the 95th percentile of the day-permuted family max.
- **A3 neighbours:** all three are net positive after cost.
- **A4 book add:**
  - primary scaled to a $30k own walk-forward drawdown and added to #463 (parity 93.81 / 3.816 asserted);
  - book ROC@$30k >= 98.50 with Sortino >= 3.816;
  - paired bootstrap 5th percentile > 0.
- **A5 twin:** primary own ROC@$30k > the own-morning twin's.

**Question to MANAGER (answer inside the 60 minutes or the bars stand as written).** MANAGER #40 says book adds are
judged forward. Should A4 be a REPORT, not a gate, for all three new-type preregs? Then a standalone pass on A1-A3 (+A5
here) would go to the pinned Auto-Validate, and the book add would wait for the forward shadow. As written, A4 is a
gate.

## What follows
- **PASS:** the same day, a BONDLEAD_1_0 plugin (harness parity to the trade first; the fund bars become a second data
  input, so the runner needs the IEF master on the job). Then a pinned Auto-Validate (date_from 2016-01-04, date_to
  2026-06-30 = the end of the fund bars, 900-trial budget over z0 and the window).
- **FAIL:** recorded dead; no other fund, window or lookback is tried.
- **Either way:** a RUNBOARD research verdict with ROC@$30k and DD%, a RESEARCH_LEDGER row and a NOISE.md note. Nothing
  live or in the adopted book changes without the owner.

## AMENDMENT 1 - house line #45 + the HALFHOUR review's #44 edits applied alike (2026-10-05 ~08:15 MST, before any real-direction run)
- **Standalone bars decide** (Auto-Validate + RUNBOARD row). A1 = own ROC@$30k >= 15, OR the earner route (own ROC@$30k >= 5 AND positive in #463's
  worst walk-forward drawdown, peak to trough on its daily series, also without the leg's 3 best days there), plus PF > 1, >= 100 trades and >= 50 a
  year, >= 6 of 9 years. A1b no-2020 = the same route holds with calendar 2020 removed (my reading of #45; MANAGER may correct). A2 null, A3 neighbours.
- **A4 is a REPORT**: it decides only whether a forward BOOK shadow line is also opened. Sized by VOLATILITY (leg daily SD over 2016-07-01 .. 2018-06-30 =
  25% of #463's daily SD on the same days), the $30k-own-drawdown version reported as the twin. Power lines recomputed BEFORE the run (same coin-flip
  leg): VOL scale (x0.807 NQ) SD 17.7, minimum detectable 29.1, four in five 44.0; $30k own drawdown (x0.759 NQ) SD 17.3, 28.4, 42.9.
- **Overlap report**: share of the leg's held 5m bars on which ORB #314 or NOISE #422 holds the same side / the opposite side (ENGU-Q 1m ETH and TTM on ES
  not included). The question in the draft is answered by #45: A4 is a report. A5 (beat the own-morning twin) stays a standalone bar.
- Unchanged: cells, rules, null, cost, stretch, no variants on a fail.
