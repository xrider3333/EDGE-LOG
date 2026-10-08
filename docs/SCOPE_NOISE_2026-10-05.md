# SCOPE - NOISE lane, 2026-10-05 (standing order addendum 2, MANAGER #54)

**What this is:** the NOISE lane's queue for the next weeks, scoped before anything runs. NOISE's own levers on NQ are
exhausted (rounds 63-70), and the NQ cash-session tape is mined for non-breakout types (new-type round 1: HALFHOUR, ROUND,
BONDLEAD dead). So the scope has three parts, as MANAGER #54 asks:
- **(A)** the NOISE mechanism on OTHER instruments as new families, each with its own crown;
- **(B)** a deep anatomy of NOISE #422 asking WHICH MECHANISM earns, not which size;
- **(C)** the weekly forward reads.

Owner decision (d), 10-05: #422 stays at 1.0x in the book, and the x1.25 line (FRONTIER Q8) is read on dollars at 36
months. Nothing here changes that.

## The mechanism, and what is already known about it elsewhere
NOISE trades a break of the day's "noise area": a band around the open, sized by how far price usually moves by that time
of day. A close outside the band means more than noise is moving the market, and the trade rides it to a VWAP exit.
- **Source:** Zarattini, Aziz & Barbon (2024), on SPY.
- **Related evidence:**
  - Gao, Han, Li & Zhou (2018): market intraday momentum.
  - Baltussen, Da, Lammers & Martens (2021, JFE): intraday momentum in 60+ futures across asset classes, strongest when
    hedgers are short gamma.
  - Li, Sakkas & Urquhart (2022): intraday time-series momentum in 16 developed markets.

**EL's evidence on other instruments (the dead list - not re-tested as is):**
- **ES, transferred** (NQ settings, nothing refit): best PF 1.126. Fails.
- **ES, re-tuned natively** (NOISE.md 2026-08-22): a 625-cell grid plus filters reached PF 1.35 in selection with a
  plateau, then lost on the single holdout (PF 0.99). Dead.
- **Funds, unchanged** (TRANSFER r2, ledger 2.49): NOISE lost on IEF (PF 0.61) and GLD (PF 0.91); FXE and USO dropped on
  data quality.
- **On NQ itself:** ES confirmation, overnight clearance, breakeven, time stop, delta, pyramids, checkpoints, tilt depth
  and short tilt are all dead (rounds 63-70).

**What is NEW here:**
- Every family in (A) gets its OWN crown on its own walk-forward stretch, never NQ's settings.
- Every Stage A prints addendum 2's diagnostics:
  - event-time path;
  - regime halves (2016-21 / 2022-25);
  - cost curve (0 / 5 / 10 / 20 bps);
  - per-year and per-episode rows;
  - long vs short.
- **Map rule of thumb (docs/MDL_MAP_R1.md):** equity-index NOISE families will tend to fall in #463's drawdown weeks with
  NQ's NOISE leg, so they need about $40k a year at a $30k own drawdown. Non-equity ones (volatility, bonds, gold,
  energy) are the ones that can sit on the "uncorrelated" ($15k) or "earner" (< $5k) rows.

## (A) The NOISE mechanism on other instruments - new families with their own crowns
**Method (the same for each family; one prereg per family):**
- **Data and stretch:** 5m RTH, Alpaca split-adjusted bars; cost charged per share as actually traded (raw / adjusted
  ratio, the TRANSFER r2 addendum). Walk-forward stretch 2016-07-01 .. 2025-06-29.
- **Grid:** a pre-registered neighbourhood of the NOISE_1_0 core (lookback, band multipliers, stop width; VWAP exit; flat
  at the close), 27-81 cells.
- **Null:** a family-wide null (time-shifted bands on the same days).
- **Bars:**
  - plateau;
  - standalone bars per house line #45;
  - book add a REPORT, incremental over the RESMOM line.
- **Pass:** a pinned Auto-Validate (900 trials) the same day.
- **Power line first.**

**A1. IWM (Russell 2000) - HELD.**
- **Why:** small caps have a different holder base (more retail, less index hedging), so the noise-area break may carry
  differently.
- **Dead-check:** ORB on IWM was flat (2.49); NOISE never ran on IWM.
- **Map:** an equity index, likely to fall with the book on the same trend days. Needs about $40k a year at $30k.
- **Expected:** own ROC@$30k 5-15. **Rank 2.**

**A2. Sector funds - NEEDS A PULL** (XLE, XLF, XLU, XLV, XLP, XLI, XLY, XLB, XLK, SMH).
- **Why:** sector moves are driven by sector news (oil for XLE, rates for XLF and XLU), so their trend days differ from
  NQ's.
- **Dead-check:** monthly sector rotation is dead (memory: rotation). That is a different horizon and mechanism. No
  intraday sector work on EL.
- **Map:**
  - XLE, XLU and XLF are the likeliest to be uncorrelated with #463's drawdown weeks.
  - XLE in 2022 is a natural drawdown-week earner test.
  - XLK and SMH are near-copies of NQ, kept as controls.
- **Expected:** small per sector. The value is a basket (A9). **Rank 3.**

**A3. Volatility ETP (VIXY) intraday momentum - NEEDS A PULL.**
- **Why:** volatility spikes trend within the day (dealers short gamma, Baltussen et al.). A noise-area break on VIXY is
  the most direct "earns while equities fall" shape in this domain.
- **Dead-check:**
  - VOLCARRY (short VIX carry, daily) is dead.
  - FRONTIER Q12 LONGVOL (long VIXY held while VIX >= VIX3M, ledger 2.59) failed. Its book gain came only from March
    2020, it lost $7.1k over #463's drawdown days, and its breadth was 3 of 9.
  - **What differs here:** both sides, intraday only, entered on a noise-area break, never held through calm days.
  - **Lesson that caps it:** crisis hedges answer March 2020 only. #463's other drawdowns are its own legs giving back
    gains. So A3 must clear the STANDALONE bars, not the earner route alone.
- **Map:** the drawdown-week earner row (March 2020 is the test).
- **Data risk:** VIXY reverse-splits often, so cost must be per actual share.
- **Expected:** uncertain, bimodal. **Rank 4.**

**A4. TLT - the NOISE FADE (the inverted mechanism) - NEEDS A PULL.**
- **Why:** NOISE on IEF lost hard (PF 0.61, TRANSFER r2), which says bond noise-area breaks REVERT. That is a different,
  testable mechanism: fade the break, exit at VWAP.
- **Disclosure:** the IEF number is SEEN, so IEF is tainted for this question. TLT is the fresh test (longer duration,
  different holders); IEF is reported only.
- **Map:** possibly uncorrelated with #463, since bond intraday reversal is not an equity trend shape.
- **Expected:** own ROC@$30k 5-20 if real. **Rank 5.**

**A5. GLD own crown - HELD.**
- **Why:** gold's price discovery sits mostly outside US hours, so the US-session band may be noisier.
- **Dead-check:** unchanged NOISE PF 0.91 (2.49). A re-tune is a new question but the prior is low.
- **Map:** uncorrelated. **Rank 7.**

**A6. QQQ own crown - NEEDS A PULL (2016 onward).**
- **Why:** QQQ is the cash twin of NQ, and the live Webull leg already trades NOISE #382 on it. This is a calibration
  read: it measures what the NQ-tuned leg should earn on QQQ (cash open auction, no overnight session, per-share costs).
  It is not a new edge.
- **Map:** not a seat. **Rank 6** (it informs the live leg).

**A7. DIA own crown - HELD.** The Dow is close to ES, and ES-native NOISE is dead, so the prior is very low. Run only as a
control beside A1. **Rank 9.**

**A8. SPY own crown - NEEDS A PULL.** SPY is the source paper's market, but ES (the same index) failed both the transfer
and the native re-tune. This is a control only, never a candidate. **Rank 10.**

**A9. A NOISE fund basket - after at least two (A) families pass Stage A.** It holds the passing families at equal risk.
The diversification comes from independent cash-session trend days. This is book-level construction, so it is a report
until the families exist. **Rank 8.**

## (B) A deep anatomy of NOISE #422 - which mechanism, not which size (HELD data, no pull) - Rank 1
This is a measurement prereg, report-only, with no rule mined from it for NQ: the old anatomy (ledger 2.1) showed that
filters mined this way are regime artifacts. The point is to name the mechanism, which then steers (A).
- **B1. Time of day.** Entries in 09:35-10:30 (opening drive), 10:30-14:00 (midday) and 14:00-15:55 (late flow): the
  P&L, PF and drawdown share of each, by regime half.
- **B2. Exit path.** P&L by exit type (VWAP / stop / end of day), the trade's best and worst point, and holding time. Is
  the money a few trend days held to the close, or many small VWAP wins?
- **B3. Day type and volatility state.** Gap vs no gap; trend day (close near the day's extreme) vs range day; FOMC / CPI
  / NFP days; prior-day range tercile; the 60-minute squeeze on / off (the part that carries inside #463 per Custom ML's
  ablation).
- **B4. Long vs short by market state.** Above / below the 200-day average, and 2022 alone.
- **B5. First break vs re-entries the same day** (cross-checks the re-entry memo).
- **Output:**
  - one paragraph naming the mechanism, e.g. "trend-day capture of opening-hour breaks in high-volatility states";
  - a list of the instruments in (A) whose day structure matches it, used to re-rank (A).

## (C) Forward reads - every week, to the RUNBOARD
- **C1.** NOISE #382 vs #422 forward ranking, and the five NOISE_422_FIXED sub-arms (full / Friday / FOMC / shorts /
  squeeze) on real and would-be fills, by the paired sequential stop. First due 10-11.
- **C2.** The x1.25 line is FRONTIER's (36 months, owner decision d). NOISE reports its leg-level numbers only when asked.

## Ranked queue (never below three live preregs)
1. **B** - #422 anatomy (held data; prereg tomorrow morning).
2. **A1** - IWM own crown (held data).
3. **A2** - sector funds, written while the pull runs.
4. **A3** - VIXY intraday momentum.
5. **A4** - TLT fade.
6. **A6** - QQQ calibration.
7. **A5** - GLD.
8. **A9** - basket.
9. **A7** - DIA control.
10. **A8** - SPY control.

## Pull list for MANAGER (through the wrapper, photograph rule: URL / time / size / sha256)
- **Symbols:** SPY, QQQ, TLT, XLE, XLF, XLU, XLV, XLP, XLI, XLY, XLB, XLK, SMH, VIXY.
- **Bars:** 5-minute RTH bars 2016-01-04 .. 2026-06-30 (the same window as the held IEF / GLD / IWM / DIA / FXE / USO
  masters), split-adjusted.
- **Daily:** raw AND split-adjusted daily closes, for cost per share as actually traded.
- **Gate:** each series passes TRANSFER r2's data gates (missing-bar share, last 5m close vs the official close within
  0.10%, no overnight gap over 25% that is not a split) before any prereg reads it.

## Queue update 2026-10-05 21:30 MST (MANAGER #64 / #65 / #66; supersedes the ranked queue above)
- **Data:** fund gates 10 of 14 pass (SPY, QQQ, TLT, XLF, XLU, XLV, XLP, XLI, XLY, XLK).
  - XLE and XLB failed once and are dropped.
  - SMH and VIXY failed twice (5m bars vs daily bars) and are out of scope; no result exists for either. A3 (VIXY) is
    gone.
- **Done:** B, the #422 anatomy (21:05). The sentence: NOISE earns on the one break of a trend day that never comes back
  through VWAP and is held to the close. See NOISE.md.
- **Queue:**
  1. A1 IWM own crown, Stage A at 07:00 on 10-06 (amendment 1 on main);
  2. A6 QQQ calibration;
  3. A2 sector funds (XLF / XLU / XLV / XLP / XLI / XLY / XLK);
  4. A4 TLT fade;
  5. A7 / A8 the DIA and SPY controls;
  6. A5 GLD and A9 basket below, unchanged.
- **Proposed by the anatomy, awaiting MANAGER's review (not applied):**
  - Order the sector funds XLK, XLY, XLI, XLV ahead of XLP, XLU, XLF: at $0.02 a share the last three pay 3 - 5% of
    their median day range, vs under 1% on QQQ / SPY / DIA / IWM.
  - Move GLD below the controls: 41% trend days, the closest to a random close.
  - Table: `tools/r37_results/noise_r422_habitats.txt`.

## Queue update 2026-10-07 (MANAGER #67 approved the habitat order; #69 / #71 QQQ round done by MANAGER)
- **Approved and applied:**
  - The sector funds run XLK, XLY, XLI, XLV, then XLP, XLU, XLF. Cost against the median day range decides (1.7 - 5.3% at
    2 cents a share).
  - GLD moves below the SPY / DIA controls.
- **A6 QQQ calibration: DONE** inside MANAGER's QQQ VALIDATE r1. CAL 0.94 (#382) / 0.92 (#422): the NQ backtest is a fair
  guide. Run #485 (NOISE family on QQQ) WEAK on PBO only. See NOISE.md "NOISE on QQQ".
- **Queue:**
  1. A2 sector funds in the order above (XLK first);
  2. A4 TLT fade;
  3. A7 / A8 DIA and SPY controls;
  4. A5 GLD;
  5. A9 basket (after two families pass).
- **A1 IWM own crown: DEAD at Stage A.** Run 2026-10-07 18:01 MST: the 10-06 07:00 launch was lost to the PC sleeping and
  was relaunched on reopening, per MANAGER #67. All 54 cells were negative, best -2.07; it is gross-flat before cost.
  See NOISE.md "NOISE on IWM r1".

## Queue update 2026-10-08 (sector funds r1 + TLT fade r1 run; STRATEGY-BEATING review #73, MANAGER #74)
- **A2 sector funds:** XLK PASSES Stage A (32.3, correlation 0.74 with NOISE #422, so the book's own NOISE on another
  tape). Its pinned 900-trial Auto-Validate follows. XLY, XLI, XLV, XLP, XLU and XLF are dead.
- **A4 TLT fade: DEAD.** Flat before cost.
- **Queue:**
  1. the XLK Auto-Validate (NOISE_1_1_FUNDGRID.py);
  2. A7 / A8 DIA and SPY controls;
  3. A5 GLD;
  4. A9 basket (needs two passing families; XLK alone does not open it).
- **What the habitat rounds have shown so far:** NOISE travels to tapes that look like NQ (QQQ 0.94, XLK) and nowhere
  else tested (IWM, five sector funds, bonds). The controls are the last equity-index check.
