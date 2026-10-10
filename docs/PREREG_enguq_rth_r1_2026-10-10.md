# ENGU-Q RTH r1 - PRE-REGISTRATION DRAFT: a market-hours ENGU-Q fit for the Webull QQQ book

**DRAFT to MANAGER, written before any number exists** (owner decision 10-09 ~20:20 MST, relayed as
MANAGER #64: "DIP + search a market-hours ENGU-Q"). Not a port of #335 - a NEW fit on a
regular-hours tape. ENGU-Q #335 itself stays live on NinjaTrader and becomes a no-order tracker on
Webull; nothing here goes near the paper book without the owner.

## Map placement, and the thing this has to beat

`docs/MDL_MAP_R1.md` prices a new leg at about $15,000 a year at a $30,000 drawdown of its own if it
is uncorrelated with BOOK #463 in the weeks #463 falls. **But that is not the relevant bar here**,
because a reference already exists and already works:

**FRONTIER's Q36 measured NQ #335's own signals filled on QQQ prints under the Webull executor, and
it keeps 98% of the leg's dollars a year at the same notional - ROC @ $30k 28.42 against the leg's
26.09, and 114.08 as a seat on the S1 line against 121.06.** So the honest bar is not "does a
market-hours ENGU-Q make money"; it is:

> **Does a fresh regular-hours fit beat simply executing NQ's signals on QQQ?**

If it does not, the owner's choice is between an NQ-signal leg that keeps 98% and a QQQ-native leg
that keeps less - and the only reason to prefer the second is operational, not financial. That
reason is real and worth stating: an NQ-signal leg makes a QQQ-only Webull account depend on a
live NQ feed and on this PC's signal path, which is a coupling the box does not have today.

## (a) The signal tape - QQQ's own prints, and why

**PRIMARY: signals AND fills on the QQQ 1-minute regular-hours master** (FRONTIER's Alpaca SIP pull,
`master_dd092f50.csv`, sha256 `bdca2595...`, 2016-01-04..2026-06-30, 1,023,757 rows).

Why that and not NQ signals with QQQ fills:

1. **The owner asked for a market-hours ENGU-Q for the QQQ book.** A fit must be fitted on the tape
   it will trade, or it is the same category of thing that already failed: #335's settings run
   unchanged on the QQQ tape made **308 walk-forward trades against the leg's 1,194** (Q36 row A),
   because thresholds calibrated to NQ's point scale and a 1,380-bar session select far fewer QQQ
   bars. Re-fitting is precisely the remedy, and it has to happen on QQQ's own prints.
2. **It removes the NQ-feed coupling** described above, which is the operational reason the owner's
   question arose at all.
3. **Q36's NQ-signal result is kept as the REFERENCE ROW, not discarded** - it is the benchmark in
   the bar below. Both are reported side by side so the owner sees the real choice.

Costs and fills, pinned now: **$0.01 a share a side** (Q36's convention), one NQ contract's notional
in QQQ shares (about 820-822), **fills 09:31-15:59 ET only, overnight hold allowed**, a signal
outside those minutes fills at the next 09:30 open (the Q34/Q36 executor rule).

## (b) The ranged file - lookbacks sized for a 390-bar session, ranges FULL

A new research file `ENGUQ_RTH_1_0.py`, the crown's mechanism with every lookback re-ranged for a
390-bar session rather than a 1,380-bar one. **The 900-trial budget is the owner's rule and is not
lowered; the ranges are NOT pinned** (MANAGER #64), so the search decides, not me.

Proposed ranges, each stated with its session meaning so the fence is auditable:

| knob | range | step | reaches |
|---|---|---|---|
| `ema_len` | 20 .. 1560 | 20 | 0.05 to 4 sessions |
| `tl_len` | 10 .. 780 | 10 | the swing-low lookback, up to 2 sessions |
| `atr_len` | 10 .. 390 | 10 | up to one full session |
| `er_len` | 10 .. 390 | 10 | up to one full session |
| `regime_len` | 1 .. 20 | 1 | days, unchanged in meaning |
| `limit_atr` | 0.0 .. 1.5 | 0.05 | unitless, the crown's 0.55 inside it |
| `buf_atr` | 0.0 .. 1.0 | 0.05 | unitless |
| `min_brk` | 0.5 .. 3.0 | 0.1 | unitless |
| `trail_frac` | 1.0 .. 4.0 | 0.25 | unitless, the crown's 2.5 inside it |
| `stop_mult` | 0.5 .. 2.0 | 0.25 | unitless |
| `act_R` | 0.5 .. 3.0 | 0.25 | unitless |
| `breakeven_R` | 0.0 .. 4.0 | 0.5 | 0 = off |
| `vol_mult` | 0.0 .. 2.0 | 0.1 | 0 = off |

**Harness gate, and it is here because this lane has already shipped this defect once:** a test
asserts every value above lands on the declared lattice (`min + step*k`), and asserts that with the
ranged file set to the crown's own settings it reproduces the crown's trade list on the NQ ETH
master trade for trade. A search space that cannot express the cell it is compared against is a
void round - that is what nearly happened to round 62.

## (c) How it is judged

One pinned Auto-Validate on the house runner: **900 trials, `date_from` / `date_to` PINNED to
2016-01-04..2026-06-30** (the pinned-validate rule; the ranges stay open), the house walk-forward /
lockbox split with the 12-month lockbox, **ROC @ $30k with DD5 beside it and the one-episode flag**
(rule 10-07), Sortino, and the house minimums of 100 walk-forward / 50 lockbox trades.

**A pass needs ALL of:**

1. **ROC @ $30k beats the Q36 reference (28.42) by more than the round's own power line**, computed
   and posted BEFORE any cell P&L. Not "beats 28.42" - beats it detectably.
2. **Sortino at least matches the reference**, and DD5 does not reveal a one-episode win (worst
   drawdown over 1.3 x DD5 = the ROC is driven by one episode and the row is reported as such, not
   passed).
3. **At least 100 walk-forward and 50 lockbox trades**, and the lockbox profitable without its
   single biggest trade.
4. **The validate's own verdict is not WEAK.** This matters more than usual - see the prior.
5. **The Webull executor read (Q34 / Q36 method) on the winning cell**, reported before any
   adoption conversation: what share of the dollars survives 09:31-15:59 fills with the overnight
   hold, and the seat read on the S1 line.
6. **A plain-exposure twin**, since this family is a long trend hold: the winning cell against a
   buy-and-hold QQQ position at the same average exposure, in-position and always-on, which is the
   comparison CALMTAPE r1 failed and the one FRONTIER's Q31 had to add after review.

**Any failure = dead, written to the ledger and the lane doc, no variants, no second search.** One
search, one budget.

## (d) The honest prior, and it is NOT encouraging

Stated before any number, with the ledger rows rather than from memory:

- **Both QQQ Auto-Validates this house has ever run came back WEAK.** Row 2.96: ORB's run **#486
  WEAK, PBO 0.976**, folds 6 of 8, and its winner differed from the live crown on 11 of 13 settings.
  Row 2.97: NOISE's run **#485 WEAK, PBO 0.687 the only fail**, folds 8 of 8, plateau 9 of 9, and
  its winner was the live core with one lookback changed. **Two for two.** A third QQQ Auto-Validate
  should be expected to come back weak, and clause 4 above takes that seriously rather than treating
  PBO as a footnote.
- **Re-searching a crown has not paid in this house before**: ORB's meta-walk-forward returned
  $166k against the defaults' $377k, which is why crowns are frozen.
- **QQQ degrades this house's NQ edges unevenly** - NOISE keeps 0.94 of its NQ edge, ORB only 0.78,
  and ORB's QQQ ROC fell to 23.4 from 35.8. There is no measurement of what ENGU-Q's mechanism keeps
  under a fresh fit, which is the gap this round fills.
- **What could make a fresh fit genuinely different from the 308-trade port:** the crown's
  thresholds are ATR multiples and break sizes calibrated on NQ's point scale over a 23-hour
  session. On QQQ's 390-bar session at roughly a fortieth of the point value, the same multiples
  select far fewer bars. A re-fit can recover the trade count, and trade count is this family's
  binding constraint (the lockbox minimum of 50 is what #335 only barely clears).
- **And what probably will not change:** this family's money is in multi-day survivors, and Q34
  already showed the overnight-hold executor keeps 100% of the exit timing's dollars while the entry
  timing's contribution is not resolvable. If the survivors are the edge and the executor already
  preserves them, a fresh entry fit has little left to win - which is the same wall seven
  pre-registered ENGU-Q entry filters hit.

**So my prior is that this search does not produce something distinguishably better than Q36's
reference, and I am saying so in advance rather than after.** The round is still worth running,
because the owner has asked, because the operational case for a QQQ-native leg is real, and because
a clean falsification closes the question instead of leaving it open.

## How this could fool us

- **900 trials on one instrument is a selection machine.** The two WEAK verdicts above are what that
  looks like. Clause 4 is the guard and the PBO number goes in the report whatever it says.
- **Overlapping sessions**: QQQ and NQ are the same underlying, so the new fit will correlate with
  #463's existing ENGU-Q leg. If it is adopted alongside, that is concentration, not
  diversification - the seat read must be incremental, never standalone.
- **The lockbox is one year and this family's lockbox is one trade.** A lockbox pass here means very
  little on its own; clause 3's without-the-biggest-trade test is the real check.
- **Cost at a cent a share is an assumption.** NOISE's QQQ work found the 6% gap was mostly cost at
  2 cents and a breakeven of $0.17 a share; a cost curve at 0.5, 1 and 2 cents is reported, not one
  number.

## What I need from MANAGER before anything runs

1. **GO or edits on the tape choice in (a)** - this is the one decision that changes the whole round.
2. **Confirmation that the Q36 reference (28.42) is the right thing to beat**, rather than the map's
   $15k-a-year row. I believe it is, because the owner's real question is which leg to put on the
   QQQ book, not whether a new leg exists.
3. Whether clause 6's buy-and-hold twin should use QQQ or the NQ proxy.

On GO this goes out as a witness branch `prereg/enguq-rth-r1` with the note and harness sha256s
posted before the run, per the run-before-main rule.

## Addendum 1 (2026-10-10, MANAGER #65 - GO, before any number exists)

MANAGER answered all three questions and this records the rulings; the draft above is otherwise
unchanged, and nothing in it is edited.

1. **TAPE: the QQQ 1-minute regular-hours master for signals AND fills.** Agreed as proposed.
2. **BAR: Q36's 28.42 is the right thing to beat** - a fresh fit must beat simply executing NQ
   #335's signals on QQQ, with **the power line posted BEFORE any cell P&L**. If it cannot beat it
   detectably, this lane says so plainly and MANAGER puts the operational choice (a QQQ-native leg
   versus the NQ-feed dependency) to the owner. The map's $15k-a-year row is NOT the bar here.
3. **EXPOSURE TWIN: QQQ**, the tape the leg trades, not the NQ proxy.

MANAGER also confirmed the running arrangements: witness branch and hashes first, then the
900-trial Auto-Validate on the house runner with the trial cache on and five workers available, and
**the #326 tree/tier re-read comes AFTER this search lands** (that re-read has since been done and
reported separately - it added 0.7 ROC points, not the 13.7 the stored block implied).

**Nothing else moves.** The ranges stay unpinned, the window stays pinned, the six pass clauses
stand as written, and the stated prior - that this search probably does not beat 28.42 detectably,
given two WEAK QQQ Auto-Validates and seven dead ENGU-Q entry filters - stands as written rather
than being softened now that the round is authorised.
