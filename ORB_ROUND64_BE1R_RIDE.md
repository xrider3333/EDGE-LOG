# ORB ROUND 64 — "breakeven at +1R, then ride" on #314 and #234: DOES NOT CLEAR (2026-10-02)

Owner idea via MANAGER inbox #20. Pre-registered before any figure: `docs/PREREG_orb_be1r_ride_2026-10-02.md`
(d4d0b830, addendum 1 baa9a84f). Tool: `tools/orb_r64_be1r_ride.py`, run from the shared checkout.

## Verdict

**Neither arm clears the bar, so nothing goes to Auto-Validate.** Both fail ROC at a $30k drawdown in the
lockbox and Sortino in both stretches. The crown #314 and the book leg #234 stay exactly as they are.

The reason is simple. **ORB already rides.** The fixed target almost never fires: 2 of #314's 2,299 trades
and 4 of #234's 2,607 in sixteen years. About seven trades in ten already end at the session close. So
removing the target changes almost nothing, and #234's breakeven is already at +1R close-armed. The owner's
rule is #234 with four trades different. For #314 the only real change is moving its breakeven from 0.5R
to 1.0R, which is what decides the result.

## Parity

Both twins reproduce their stored lockboxes exactly. #314 needed its cold replica (addendum 1): its stored
lockbox predates the v73.841 warm-start fix, so it reads 4,605.081 points cold against 4,356.581 warm. The
round uses the warm series. The BOOK #463 re-run of the #234 leg also matches the stored book.

## Figures (one contract; ROC %/yr at a $30k daily-valued drawdown; walk-forward 2016-07-13..2025-08-12, lockbox 2025-08-13..2026-08-13)

| | WF ROC | WF Sortino | WF net | WF DD | LB ROC | LB Sortino | LB net | LB DD |
|---|---|---|---|---|---|---|---|---|
| #314 (twin) | 35.3 | 2.20 | $308,124 | $28,857 | 114.1 | 3.06 | $87,132 | $22,925 |
| **P1** #314 + breakeven 1.0R + ride | 37.3 | 2.17 | $313,841 | $27,766 | **96.6** | 2.91 | $86,722 | $26,962 |
| D1 #314 + breakeven 1.0R, target kept (reported) | 37.5 | 2.18 | $314,951 | $27,766 | 96.6 | 2.91 | $86,722 | $26,962 |
| D2 #314 + ride, breakeven 0.5R kept (reported) | 35.1 | 2.19 | $307,014 | $28,857 | 114.1 | 3.06 | $87,132 | $22,925 |
| #234 (twin) | 34.2 | 2.08 | $301,510 | $29,142 | 103.8 | 2.99 | $88,943 | $25,723 |
| **P2** #234 + ride | 34.2 | 2.08 | $301,845 | $29,142 | **83.1** | 2.40 | $71,178 | $25,723 |

- **P1** gains 2 points of walk-forward ROC (a slightly shallower drawdown) but loses 17.5 points in the lockbox.
  Lockbox money barely moves (18 trades change, 8 better and 10 worse, net -$410). The loss comes from the
  drawdown, which deepens from $22.9k to $27.0k. Its Sortino is lower in both stretches. By calendar year it is $7,953 behind #314 (5 of 15 years better),
  and its paired per-trade gain is noise (t 0.12, negative without its best trade). D1 equals P1 to within one
  target hit and D2 equals #314, so the whole effect is the breakeven move, not the ride.
- **P2** changes 4 trades in sixteen years. One is the lockbox trade of 2026-06-09: the twin took $25,234 at the
  5.5R target, while the arm rode on and closed at $7,469. That one trade, -$17,765, is the whole lockbox gap.
  The other three move -$745, -$40 and +$1,120.
- **R figures did not mislead here.** The trap the prereg guarded against (a breakeven shrinking the average loss)
  runs the other way for P1: the later breakeven scratches fewer trades (117 against 333), so the average loss grows.
  The verdict rests on dollars either way.

## BOOK #463 with the ORB leg swapped (reported; book bar from round 63)

Unified convention on round 63's windows. On these windows #463 reads WF 94.0 / LB 155.5; Frontier's reference
is 93.8 / 155.5.

- **P2** (#234 + ride): WF 94.0 / LB 144.8, Sortino 3.88 / 3.93 against 3.88 / 4.22. **FAIL.** The book keeps #234.
- P1 (#314 + breakeven 1.0 + ride): WF 119.4 / LB 144.0. **FAIL** on the lockbox, the same way #314 itself failed
  in that seat (Frontier run #473).

## What this closes

The owner's exit idea is already how ORB trades, apart from the breakeven trigger. Whether to move the breakeven
was settled earlier: #314's 0.5R came from its own search, and #239's 0.8R from round 63, now on shadow paper as
ORB_239. Any further sweep of the breakeven would fall into the breakeven trap. **DEAD for both seats; do not
re-test a no-target ORB variant.**
