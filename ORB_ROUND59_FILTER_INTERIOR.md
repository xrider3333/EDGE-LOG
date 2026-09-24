# ORB round 59 — #257's volatility filter is eleven trades wide (2026-09-24)

Driver: `tools/orb_r59_filter_interior.py`, results `_r59_filter_interior.csv`.
Full window 2010-06-07 → 2026-08-13, NQ 5m RTH no-adjust, one contract, 0.533 points per round turn.
55 cells: the volatility filter from off to 0.80, crossed with the stop from 2.00 to 3.00, at run
#257's other settings. Scored the way the house now judges — money by calendar year against the
control — not on a ratio.

## The question this answered

The family's money moves with how hard the volatility filter gates, and looser earns more. But the
direction does not run to the end: run #266, which turns the filter off, earns less than run #257,
which merely loosens it to 0.50. Three coarse samples cannot say whether that is a real interior
peak or noise. This mapped the whole span.

## What the map shows

| Volatility filter | Trades | Net | vs the control | In the four biggest years | Worst year |
|---|---:|---:|---:|---:|---:|
| off (and 0.10, 0.20, 0.30, 0.40 — **identical**) | 2,762 | $409,912 | +$20,038 | +$12,736 | −$7,528 |
| **0.50 — run #257** | 2,751 | $416,382 | +$26,507 | +$17,138 | −$7,528 |
| 0.55 | 2,731 | $402,603 | +$12,728 | +$8,160 | −$9,745 |
| 0.60 | 2,689 | $399,880 | +$10,006 | +$8,508 | −$14,098 |
| 0.70 — the control's setting | 2,547 | $385,256 | −$4,618 | −$645 | −$10,449 |
| 0.80 | 2,305 | $373,111 | −$16,763 | −$22,282 | −$8,651 |

Read at run #257's stop of 2.50. The pattern is the same at every stop width tested.

**Every setting from off up to 0.40 produces the byte-identical result.** The gate never binds below
0.45, so "no filter" and "filter 0.40" are the same strategy. That makes run #257's setting of 0.50
the first value that does anything at all — and the only one that helps.

## Why that is a spike and not a plateau

- Moving the filter from inert to 0.50 removes **eleven trades out of 2,762** and adds $6,470.
- Moving it one step further, to 0.55, removes twenty more and gives back $13,779.
- So the entire advantage of run #257 over its no-filter sibling sits on eleven trades, with a cliff
  on either side. One grid cell wide.

**The null.** Removing eleven trades drawn at random from the same population produces a change at
least this good 8.5% of the time (20,000 draws, p = 0.085). That does not clear any bar this stack
uses.

**Worse, it is not a live-forward effect at all.** The eleven trades run from 2014-05-30 to
2021-07-06. Three of them, worth $4,402 of the $6,470, land in 2021. **The filter has not removed a
single trade in the last five years.** Whatever it did, it cannot do it going forward.

## What survives, and what does not

Run #257 beats the control by $26,507 over the window. That splits cleanly:

- **$20,038 is robust.** It comes from the wider stop (2.50) and the bigger breakout buffer (0.30),
  and it is identical across five different filter settings. It is also ahead in the four biggest
  years by $12,736, and it lifts the worst year from −$14,299 to −$7,528.
- **$6,470 is fragile.** It is the filter at exactly 0.50: eleven trades, eight of them losers, none
  since July 2021, p = 0.085, with a cliff one step in either direction.

Separately, **loosening the filter is itself robust** and should not be confused with the spike:
going from the control's 0.70 down to inert is worth $24,656 across 215 trades, not eleven. Tightening
it costs money all the way up, exactly as the walk-forward money across the family already said.

## What this changes

1. **Runs #257 and #266 should be treated as the same strategy.** They differ by a filter setting
   that has been inert since 2021. #266 — the same geometry with the filter off — is the more honest
   of the two, and the $6,470 it gives up is money that could not be earned again.
2. **The ranking's #1 pick does not change, but the reason for it does.** #257 leads because of the
   wider stop and the bigger buffer, not because of its filter. `ORB_BEST_WF.md` carries a correction
   to that effect.
3. **The queued validate is well aimed.** The E1-region file fences the filter at 0.40–0.60, which
   straddles the spike, so the walk-forward has to re-pick 0.50 inside every fold. If eleven
   pre-2021 trades are all it is, it will not hold up, and the run will say so.
4. **The stop of 2.50 is the broad part of the ridge.** It is the best stop in the big-four-years
   column at every one of the eleven filter settings tested, which is the kind of agreement the
   filter setting conspicuously lacks.

## Discipline note

This was pre-registered as a shape read, not a crown hunt, and it stayed one. One cell of 55 beats
#257 on money against the control (filter 0.50 at stop 2.00, +$28,710) and it is not recommended:
it buys $2,203 with $3,096 more drawdown and a worse worst year, and it sits on the same eleven-trade
spike. This session's meta walk-forward over eleven forward years found re-picking these parameters
has no forward skill, so a surface maximum is a coordinate, not a recommendation.
