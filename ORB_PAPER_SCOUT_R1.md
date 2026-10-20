# ORB PAPER SCOUT r1: new ORB-fit papers vs the dead list (ORB lane, 2026-10-20)

**Verdict: NOTHING SURVIVES.** One rule passed the pre-WF map, but it is a tighter stop under another name, and its gain is drawdown shape.
REPORT only. Pre-WF rows only; no WF or lockbox number was computed for any new idea.

**Why a paper scout.** The reading shelf has no ORB-fit item left after Nos. 4 and 17. FRONTIER's book-lift scout r1 (10-16) found
nothing with five lenses on held data, and said a next round should start from new data, a new survivor or a new paper. This round
looks for papers.

**How** (one workflow, `C:\EdgeLog\_anatomy_cache\wf_orb1020\workflow_result.json`, per-agent files beside it):
- Three web scouts, one per lens: opening range and failed-break fades; predicting trend days at the open; trade management and
  execution. Each candidate was checked on a fetched page; no PDF was downloaded.
- A dead-list critic checked each one against RESEARCH_LEDGER, the 289-entry tested catalogue and the shelf.
- Each survivor got a power-first pre-WF map, then two refuters (implementation / look-ahead; novelty / one episode / cost).

**The 13 distinct sources and why each died** (15 candidates, two duplicate pairs merged):

| Source (as the scouts found it) | Why it is dead or covered |
|---|---|
| Subhani 2026, ORB on event-free Fridays (SSRN 7589980) | #314 with re-tuned knobs (30-min OR, weekday and event filters). or_bars is a spike, calendar filters are 0/18, about 20-30 trades a year |
| Mesfin 2026, volatility-volume-gap regime classifier for MNQ (arXiv 2605.11423) | Fires about 10 days a year. Gap, drive, RVOL and GAP38 parts are dead. The author's own results flip sign by year |
| Pineda 2026, anatomy of the retest in the QQQ ORB (SSRN 6745958) | Descriptive, no P&L. The retest exit is the breakeven knob in disguise, and the late-retest arm is the dead stale-out |
| Pagani & Zarattini 2026, "Fast Alphas" tactical overlay | Pre-WF: no reversion after #314's entry to harvest. Dominated by the dead PULLBACK / limit-back / late-fill rows |
| Wu et al. 2026, ORB with an LSTM true-range forecast | An open-anchored k x range breakout = EXPAND (dead). Vol buffers are dead, and HAR beat the house range forecaster |
| Fetna 2026, ORB does not survive costs, 225 cells (SSRN 7428398) | A critique, not a rule. It repeats house findings (ETH / London ORB dead, 1-min ORB fragile) at 2.3x house cost |
| Mesfin 2026, structural limits of OHLCV momentum in MNQ (arXiv 2605.04004) | A critique at a 2.0-pt cost floor (about 4x house). Its positive controls are only in the PDF; London ORB is dead here |
| Krueger 2026, shelf No. 4 replicated on five indices (mql5 blog) | A replication of No. 4 (gross reproduced, net zero), already cited in ORB_SHELF04_ZARATTINI.md |
| Kurth, Eisler, Rej et al. 2026, demise of short-term trend following (arXiv 2607.01550) | Its prediction fails on house data twice: ORB on NQ is improving while tick/ATR shrank, and ES ORB is dead. Decay = DECAY r1 |
| Tsai et al. 2019, timely ORB on index futures (IEEE Access) | ORB with the OR length as the only knob = #314 with a re-tuned or_bars, a spike |
| Concretum 2026, "How to Manage an Intraday Trend Trade": session-open, PSAR and ensemble arms | Session-open = a re-tuned close stop (3 of 6 folds, does not earn when #463 falls). PSAR's AF is unpublished. The ensemble is an average of near-copies |
| Zarattini & Aziz 2023, VWAP "holy grail", used as a VWAP exit for ORB | Fails on #463's own leg (#234 leg ROC -0.12 -> -1.05). The +9.78 book read is max-DD shape on money that falls. The VWAP family is closed |
| Maroy 2025, intraday momentum exit strategies (forum / SSRN) | The VWAP arm is a duplicate; the ladder exit is undefined; staged partial exits are dead in every lane |

**The one survivor: a session-midline exit on #463's ORB leg** (Concretum 2026, midline arm).
- **Rule.** Exit a long at the next open if a 5m close falls below (running RTH high + low) / 2; mirror for shorts. k = 0.5 is the
  primary, with 0.65 and 0.8 as neighbours fixed in advance.
- **Map** (`wf_orb1020\screen-1\map.py`). The build matches the book's L0 to $0.00.
  - #234 with the exit: gross/cost 0.96 -> 1.92; leg ROC@30k -0.12 -> 9.73.
  - Swapped into #463: book ROC 47.27 -> 67.78 (+20.51, SD 9.07). That passes the mechanical gate.
- **Refuter 1 (implementation): not refuted.**
  - No look-ahead. All 616 cuts fill at the next open. Cost is taken once.
  - It found the fatal control, though: a plain close-checked stop 0.7 OR widths from entry does the same (gross/cost 1.96, book
    swap +19.88). The midline adds +0.63, under the +2.36 bar.
- **Refuter 2 (novelty / one episode / cost): REFUTED.**
  - It is a tighter stop, and stops and trails on ORB are on the dead list (#234 was built with the trail OFF; catalogue 136 / 142 /
    144 / 159; ORB.md X14).
  - Of the +20.51, +15.06 is the book's worst drawdown shrinking (2013); the net part is +5.45.
  - One fold carries it: 2015-07..2016-06 is 133% of the leg's money change, and the other five folds sum to -$3,255.
  - It loses where ORB's money is: -576 pt on the top-5% move days, and it cuts 14 of #234's 49 biggest winners.
  - k = 0.5 sits one step from a cliff (k = 0.35 loses money).

**Frame lesson (for every pre-WF ORB read).** On the pre-WF stretch the book rewards any cut in ORB exposure. Dropping #234 adds +17.81. A
trail_bars = 8 exit that LOSES money on the leg scores +16.39, and k = 0.35 loses $755 yet scores +8.37. So the +2.36 pre-WF book bar
cannot judge an ORB-slot swap, filter or exit. Such a candidate also needs:
- the leg's own net change > 0 and spread over folds;
- a plain tighter-stop control;
- not one episode.

Nothing is queued. No run record for the scout (the screen's leg reads are pre-WF maps of an exit already on the dead list).
