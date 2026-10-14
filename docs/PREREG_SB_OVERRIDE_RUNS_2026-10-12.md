# OWNER-OVERRIDE RUNS 10-12 - three NQ scalp cells re-run, and MEGACAP-EARN as a real walk-forward run (STRATEGY-BEATING)

**Why this runs at all (record: owner override 10-12).** The owner asked "what was the roc/yr on those tested. Keep testing
them" (MANAGER #169). All of these cells closed at draft or died in triage. The power-first gate is overridden for these
cells only, because they are cheap. Nothing here is a candidate for the book unless a later, separate prereg says so.
Written before any of these runs; harness `tools/rocfrontier/r30_override_1012.py`.

## Common rules
- **Data:** NQ 1m RTH no-adjust master (`db_noadj_rth`), 2010-06-07 .. 2026-10-09, the newest COMPLETE session on file
  (10-12 was still trading). One NQ contract, $20 a point.
- **Stretches:**
  - **WF** 2016-07-01 .. 2025-06-29 (the house walk-forward stretch) decides any reading.
  - **AFTER** 2025-06-30 .. the newest bar is reported apart. It is the house lockbox (already spent) plus the
    months since, and is never a pass by itself.
- **Costs:** primary 0.783 pt a round trip ($15.66 = $5.66 commission + 1 tick each side; the owner's rule, as TTM r25 used
  on ES). Cost curve reported: gross 0 / house 0.533 / 0.706 (TV's $4.12 commission) / 0.783 / MNQ 1.20 per NQ-equivalent.
- **Per stretch, at the primary cost:** ROC @ $30k, DD5 (and the one-episode flag), DD % from peak (one contract on a
  $100k account), Sortino (daily), win rate, average win / average loss, trades a year, median hold. All come from the
  house helpers (`seat_pipeline.figures`, `drawdowns.dd_pct_peak`).
- **Daily P&L:** every session of the master is a row; a trade's P&L is booked on its session; no-trade days are 0.

## A. The three scalp cells (rounds 37-38, re-run)
- **Pick rule, fixed now from the stored triage files:**
  - Pool: fixed-target cells only (T1 / T2), since these are the scalps; ride-to-close cells are not.
  - Ranking: highest GROSS dollars a trade.
  - At most one cell per mechanism.
  - Round 38's fixed cells are all below round 37's.
  - Result: **M4 RANGE-BURST x4 / T1** ($32.36 gross a trade, 674 trades, hold 11 min), **M3 PDH/PDL stop 0.10 / T2**
    ($13.75, 3,489, 7 min), **M1 MICRO-ORB or5 / first / T1** ($5.80, 2,664, 22 min).
- **Rules:** round 37's own code for these three cells, copied unchanged except that each trade's session is recorded.
  - Every decision is on a finished 1m bar; entry is at the next bar's open.
  - Inside a bar the stop is checked first; targets fill at the target price.
  - Each cell keeps its time stop (30 / 60 / 30 min) and is flat at the close.
  - Round 37's roll-seam detector skips the same sessions.
- **Parity gate (before any number is read):** on round 37's own window (2010-06-07 .. 2025-06-29) at zero cost, each
  cell must reproduce the stored GROSS file's trade count and net to the dollar. Otherwise the run stops.

## B. MEGACAP-EARN (NQ the session after a mega-cap earnings release)
- **Events:** EDGAR 8-K item 2.02 releases from TV's calendar (`earnings_calendar_ndx.csv`, true-UTC acceptance stamps).
  - Kept: timing `after-close` or `pre-open`, reaction sessions 2016-06-01 .. 2026-06-30.
  - Dropped: `intraday` releases.
- **Mega-cap, point in time:** the company is a Nasdaq-100 member that month (`tools/data/ndx_members.csv`). It also
  ranks in the TOP 9 members by mean dollar volume (raw close x volume, summed over its share classes) over the 60
  sessions before the reaction session (Alpaca daily bars). Dollar volume stands in for index weight; no future data is
  used.
- **Signal:** the company's opening gap on the reaction session = split-adjusted open / prior split-adjusted close - 1.
  - Several events on one session add their gaps.
  - **Side = the sign of that sum (CONTINUATION, the primary reading).** The mirror (fade) is reported, never chosen.
- **Trade:** NQ enters at the open of the 09:31 bar (the gap is known at 09:30) and exits at the session's last RTH bar
  close. One trade a session. No stop.
- **Expected (map, 10-12):** about 36 events a year; median own ROC 1.9. A ROC under 15 on WF is DEAD.
- **Window note:** stock data ends 2026-06-30, so B's AFTER stretch ends there.

## C. AUCTION-1300 - NOT RUN (data)
The held Treasury file (`treasury_auctions_raw.json`, TV 10-05) carries the auction schedule and size but not the
results: no bid-to-cover, no high yield. The rule as mapped needs the bid-to-cover. Fetching it is a new download, and
the owner said no new data on 10-12. **This needs an owner call** - a free public fetch by TV's fetcher, or leave it
unrun. A size-only variant would be a different idea and is NOT substituted.

## What follows either way
- Results go to MANAGER as a read first, with the four numbers per stretch.
- Then one ledger line. The ledger ship waits until MANAGER says the priority ships have landed.
- Nothing changes in augur_engine.

## Addendum 1 (10-12, before any number was read)
The first start stopped at its seam step: round 37's roll-seam detector was retired by the 10-08 roll fix
(`augur_engine.rolls`), and its replacement needs a roll context.
- **Change:** seam sessions now come from the house's TRUE roll calendar. The call is wrapped in
  `rolls.roll_context("NQ", bar times, 60)`, the same calendar the engine applies to every run.
- **Parity reference:** the roll audit's restatement of round 37 on that calendar
  (`rollaudit/work/harness-r35-38/r37_scalp_triage_true.csv`), at its 0.533 pt cost:
  - M4 x4/T1 677 trades / +$13,403;
  - M3 stop0.10/T2 3,468 / +$9,410;
  - M1 or5/first/T1 2,659 / -$20,155.
- The stored GROSS figures in section A came from the old detector; they still pick the cells, unchanged.
- Nothing else changes.

## Addendum 2 (10-12, before any result was read)
The second start stopped at the parity gate. M4 and M1 matched to the dollar; M3 matched its trade count (3,468) but
netted $9,333 against the audit's $9,410 at 0.533 pt. No WF, AFTER or MEGACAP-EARN figure was computed.
- **Cause, found:** the NQ master gained 349 bars after the roll audit ran (09-25). They fill a hole on 2020-06-30 from
  10:11 to the close. No existing bar changed, and no other bar inside round 37's window was added or removed.
  - The filled session moves M3's prior-day high / low for 07-01 and its 20-day range average for 20 sessions.
  - M1 and M4 do not read those levels, so they are unchanged.
- **Proof the code is a faithful copy:** on the master copy saved before the fill
  (`augur_uploads/NOADJ_NQ_1m_RTH.csv.bak-20260717`, sha256 848991b653a217da...), the harness gives 1,485,957 bars,
  3,868 sessions and 61 seam sessions (the audit's own log line) and all three cells match the audit to the dollar.
- **Change:** the parity gate now runs on that saved copy, checked by its sha256 and by the audit's bar, session and
  seam counts. The gate still refuses on any mismatch.
- **The readings themselves use the CURRENT master** (hole filled), through 2026-10-09, as written above.
- Nothing else changes.

## Addendum 3 (10-12, before any P&L was computed)
The third start passed the parity gate (all three cells to the dollar on the pinned copy), then stopped at its first
stretch: the session dates carried the master's Eastern time zone and could not be compared with the plain stretch dates.
- The only output before the stop was M1's trade count on the full window. No P&L, ROC or win rate was computed.
- **Change:** session dates are plain dates. The same fix stops B from silently matching no sessions.
- **Disclosed, not changed:** B's event file counts every 8-K carrying item 2.02, as written above. Tesla files its
  quarterly delivery reports under 2.02 as well, so it has about 78 events instead of 40. Those stay in.
- Nothing else changes.
