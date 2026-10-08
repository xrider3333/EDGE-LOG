# SCOPE - ENGU-Q lane: the ETH session as a mechanism space (standing order addendum 2)

Written 2026-10-07 against the 10-05 order (MANAGER #43 item 1, #44 item c). The crown ENGU-Q #335
is **frozen** and its entry direction is closed by the owner (10-02), so this lane's new work is a
different domain, not another ENGU-Q variant: **the 23-hour electronic session itself** - overnight
auction structure, the Asian-to-European-to-US hand-offs, and pre-open positioning.

## The one constraint that shapes everything below

The model map (`docs/MDL_MAP_R1.md`) prices a new leg: **about $15,000 a year at a $30,000
drawdown of its own if it is uncorrelated with #463 in the weeks #463 falls; about $40,000 if it
falls with the book; and under $5,000 if it EARNS while the book falls.** The map also says
plainly that "another NQ/ES momentum leg falls in the same weeks the book does".

**That prunes most of this domain before any test.** The best-known ETH regularity - that the
overnight return carries much of the index's long-run premium - is a long momentum bias on the same
instrument as three of #463's four legs, so even if it works it lands in the expensive row. And the
opposite trade is already dead: **short-growth insurance FAILS the yardstick**
(`edgelog-short-growth-insurance-fails-yardstick`) because the 2019-21 bleed became a new worst
drawdown. So the mechanisms worth drafting here are the **direction-agnostic** ones: structures
that fire long and short out of the same rule, which is how a leg can earn in a falling week
without paying a permanent short's carry.

## Dead-list cross-check for this domain, done before the list

- **GAPGO is dead.** Anything about the overnight gap at the RTH open must say how it differs. Every
  candidate below that touches the open is specified on the **ETH session's internal structure**,
  not the gap's sign or size, and the two that trade near the open trade *against* the overnight
  move rather than with it.
- **Seven ENGU-Q entry filters are dead** and the direction is owner-closed. Nothing below refines
  an ENGU-Q entry; these are separate strategies with their own trades.
- **SPREAD r2, NQBRD r2, TRANSFER r2, VOLCARRY r2, REVERT r2 are dead** (ROC hunt). The ES-versus-NQ
  idea below is an **open-auction convergence** with a holding period of minutes, not a continuous
  spread position, which is what SPREAD was.
- **Owned by other lanes, not duplicated here:** the rates hand-off (BONDLEAD r1, NOISE lane),
  half-hour seasonality (HALFHOUR r1), round numbers (ROUND r1), the daily/multi-day downside
  continuation side of the drawdown-week hunt (STRATEGY-BEATING leads; TV has the daily-bar side).
- **Quiet-tape conditioning on the RTH open belongs to ORB** (`edgelog-orb-quiet-tape-standdown`);
  candidate 10 below is therefore routed, not drafted.

## The mechanism space - 14 candidates

Data column: **HELD** = masters or caches already here; **PUBLIC** = no-key public source; **PULL**
= needs MANAGER's wrapper. Map row: **DDW** = aimed at the drawdown-week earner row (helps under
$5k/yr), **UNCORR** = needs about $15k/yr, **SAME** = falls with the book, needs about $40k/yr.

1. **ASIARANGE - Asian range, European break.** The 18:00-02:00 ET range is built by the thinnest
   book of the day; a break of it during European cash hours (02:00-05:00 ET) is where real size
   first arrives. Fires long and short. HELD (NQ/ES 1m+5m ETH). UNCORR. ~200-250 trades a year.
2. **EUREV - the European move handed back at the US open.** Moves made 03:00-08:00 ET are partly
   provided for by US liquidity at 09:30-10:30 ET. Mean-reverting and direction-agnostic, so it is
   the most plausible DDW candidate in the domain: in a falling week the European leg is usually
   down and this trades the bounce. HELD. DDW. ~250 trades a year.
3. **ONVWAP - overnight VWAP reversion into the open.** Distance from the ETH session's own volume
   -weighted average at 09:00 ET, traded back toward it. Direction-agnostic. HELD. UNCORR. ~250/yr.
4. **ESNQOPEN - overnight dispersion convergence.** When ES and NQ disagree overnight in beta terms,
   trade the laggard toward the leader in the first 30 RTH minutes. Relative value, so structurally
   uncorrelated with a single-index book. HELD (both masters). UNCORR, possibly DDW. ~250/yr.
5. **VALUEREJ - prior-ETH value-area edge rejection.** Time-at-price over the ETH session gives a
   value area; a return to its edge that is rejected is the Market Profile reading of overnight
   structure. Direction-agnostic. HELD. UNCORR. ~150/yr.
6. **MACRO0830 - the 08:30 release imprint.** The 08:30-09:00 ET reaction to a scheduled release,
   and whether the 09:30 open continues or retraces it. Needs a release calendar. PUBLIC (FRED /
   BLS release dates). DDW on the retrace side. ~120/yr (release days only).
7. **SETTLE1600 - the post-settlement re-open.** The 15 minutes after the 16:00 ET settlement, when
   the ETH book re-forms with no RTH reference. Direction-agnostic. HELD. UNCORR. ~250/yr.
8. **SUNOPEN - the Sunday 18:00 seam.** The weekend gap and the first two hours, with the weekend's
   news already in the first print. Direction-agnostic. HELD. UNCORR. ~50/yr - **fails the 50
   sealed-trade minimum on its own** and can only ever be a component, which is stated here rather
   than discovered later.
9. **ONCONC - overnight volume concentration.** Sessions whose volume is unusually concentrated in
   one window versus spread evenly, as a state variable for what the RTH session does. HELD.
   UNCORR. A state study first, not a strategy.
10. **QUIETNIGHT - narrow ETH range into an RTH trend day.** ROUTED TO THE ORB LANE, not drafted
    here: it conditions the RTH open, which is ORB's seat and already has a stand-down rule.
11. **ONDRIFT - the plain overnight long.** The well-known close-to-open premium. NOT DRAFTED: it is
    a long NQ momentum bias, lands in the SAME row at about $40k/yr, and the map says this kind of
    leg does not clear both stretches even at $80k. Recorded so nobody drafts it later.
12. **ONSHORT - a persistent overnight short as insurance.** NOT DRAFTED: the short-growth insurance
    result already failed the yardstick for exactly this shape.
13. **FXHANDOFF - the dollar's European session leading NQ's open.** Would be a genuine hand-off
    mechanism, but **the data is not held**: there is no intraday FX or European index future in
    this repo. PULL (and probably not free). Parked pending a MANAGER view on cost.
14. **CARRYNIGHT - overnight funding/roll-window effects.** Only two roll windows a quarter and the
    offsets are now exactly measured, so the tradable residue is small. HELD. Low priority.

## Ranked order, and the queue of three

**Rank 1 - EUREV**, because it is the only candidate that sits squarely on the drawdown-week earner
row, which the map says helps at almost any positive return, and it needs no data we do not have.
**Rank 2 - ASIARANGE**, the cleanest pure session-structure mechanism and direction-agnostic.
**Rank 3 - ESNQOPEN**, structurally uncorrelated by construction (relative value), which is the
other way onto the cheap row.
Then ONVWAP, VALUEREJ, SETTLE1600, MACRO0830; ONCONC as a state study; SUNOPEN only as a component.

**Preregs to write, in this order, each with the power line first and a family-aware null:**
EUREV r1, ASIARANGE r1, ESNQOPEN r1. Walk-forward only, Stage A, cost curve at 0 / 5 / 10 / 20 bps,
regime halves, per-year and per-episode rows, long versus short split, and DD5 beside every ROC.

**The family-aware null this domain needs**, said once here: these are all *clock-window* rules, and
a clock window on a trending instrument will show a return simply because the instrument trended.
Each prereg's null is therefore **the same rule on shifted windows** (the same durations moved one
and two hours earlier and later), not a random-trade null, so the claim is that the SESSION BOUNDARY
matters rather than that the hours were lucky.

## What this lane needs from MANAGER

- A view on candidate 13: intraday FX or European index futures are the one dataset that would open
  true hand-off mechanisms, and nothing here can substitute for it.
- Confirmation that candidate 10 goes to the ORB lane rather than being drafted here.
- Nothing else is blocked; ranks 1 to 3 run on held data.

## Addendum 1 (2026-10-07, before any number was run) - THE DOC ABOVE IS WRONG AND THIS LANE HAS NO BACKTEST SHOT

Never edited, appended per the house rule. **The dead-list cross-check above was written from this
lane's memory index instead of from `RESEARCH_LEDGER.md`. Reading the ledger afterwards shows the
domain is already closed by name.** Posted to MANAGER before the doc was reviewed.

What the ledger says about the space this doc proposed:

- **Row 2.75** (DD-WEEK r1 OVERNIGHT, TV's prereg, run in-house): dead, 0 of 12 cells, and its
  recorded lesson is that with DAILYFADE (0 of 8) and row 2.13 **"the overnight seat is closed"**.
  That is a house verdict on this doc's entire domain and the doc does not cite it.
- **Row 2.15**: European-morning momentum on the 24-hour tape - the sign of 02:00-04:00 ET
  predicting 04:00-09:25 - **momentum loses $39 a trade (2 of 16 years) and the FADE is +$8 a trade
  after cost. Dead.** That is rank 1 (EUREV) and rank 2 (ASIARANGE) above, already measured. At $8
  a trade and ~250 trades a year that is about **$2,000 a year against the map's $15,000** for an
  uncorrelated leg. Neither is new and neither is big enough.
- **Row 2.33 (WKND)**: the weekend gap on the Sunday reopen, 18 cells, dead. That is SUNOPEN, which
  this doc demoted for sample size when it should have called it dead.
- **Row 2.90**: "the VWAP family stays closed." That is ONVWAP.
- **Row 2.43** (NOISE r67): the overnight high and low as a clearance condition, dead.
- **Row 2.13**: the overnight dealer-inventory drift, dead for ROC; ONDRIFT died at PF 1.205. The
  doc reached this one by reasoning (candidate 11) - the ledger has the number.
- **Row 2.4**: NQ-versus-ES feature families carry nothing.

**What survives, honestly: three of fourteen, all with weak priors.** ESNQOPEN (an ES-versus-NQ
open-auction convergence over the first 30 RTH minutes - adjacent to row 2.4 and to the dead SPREAD
r2 rather than identical to them), MACRO0830 (the 08:30 ET release reaction into the open, needs a
public release calendar), SETTLE1600 (the 15 minutes after the 16:00 settlement). A tiny window and
two adjacencies to dead rows is not a queue of three.

**Conclusion, invoking item 7 of the standing order: NO BACKTEST SHOT in this domain.** This lane
will not re-test rows 2.15, 2.33 and 2.90 under new names, and will not dress one weak candidate up
as three. The cross-lane assignment stands instead: second reviewer (the NOISE hedge-tilt review of
2026-10-07 carried the duty-cycle measurement that lane needed; the 10-04 roll-premise catch stopped
a book run), the #335 guard with the S1/S2 forward reads, order-flow scoring and data QA. If MANAGER
wants one ESNQOPEN prereg regardless, it gets written with the weak prior stated first and the
shifted-window null described above.

**The general lesson, and it is the fifth instance of one failure shape in this lane: the memory
index is a pointer, not a source.** It is written short, so it cannot carry the numbers that decide
whether an idea is new. Before calling anything untested, open the ledger row.
