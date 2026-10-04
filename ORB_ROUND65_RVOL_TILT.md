# ORB ROUND 65 — breakout-bar volume size tilt: FAILS STAGE A on #314 and #234 (2026-10-04)

The owner asked via MANAGER for the frontier to be pushed, with one best remaining ORB shot. Pre-registered and
reviewed twice by MANAGER (GO with edits), then put on main before any real figure: `docs/PREREG_orb_rvol_tilt_2026-10-04.md`,
f876d028. Tool: `tools/orb_r65_rvol_tilt.py`, run from the shared checkout.

## Verdict

**Both arms fail Stage A on every walk-forward test, so there is no lockbox read and no Auto-Validate.** The
breakout bar's volume does not help ORB. Taken at face value it hurts, but that reading is post-hoc and not
significant, so it does not justify an inverse rule (see below).

**This was ORB's one frontier shot, and it is dead. The ORB lane's frontier work is now the forward shadows
only: #239, #257 and the order-flow test.**

## Parity

Both twins reproduce their stored lockbox counts and points exactly from the cold replica, and the round's
#234 trades equal #463's stored ORB leg to the cent, day by day. No lockbox figure of either arm was computed.

## Stage A (walk-forward 2016-07-13..2025-08-12; ROC %/yr at a $30k daily-valued drawdown)

| | WF ROC | Sortino | net | DD |
|---|---|---|---|---|
| #314 raw | 35.3 | 2.20 | $308,124 | $28,857 |
| **P1** #314 + tilt | **29.7** | 1.78 | $278,670 | $31,020 |
| #234 raw | 34.2 | 2.08 | $301,510 | $29,142 |
| **P2** #234 + tilt | **24.8** | 1.65 | $266,359 | $35,523 |

| Stage A bar | P1 | P2 |
|---|---|---|
| ROC higher | FAIL (-5.6) | FAIL (-9.4) |
| Sortino higher | FAIL | FAIL |
| 100 trades | pass (1,290) | pass (1,455) |
| family null, shuffle / time-shift 95th pct | FAIL (+10.5 / +9.5 needed) | FAIL (+3.6 / +4.3 needed) |
| block bootstrap 5th pct > 0 | FAIL (-25.7) | FAIL (-24.0) |
| breadth, paired d > 0 in 6 of 9 years | FAIL (3 of 9) | FAIL (2 of 9) |
| without Feb-Apr 2020 | FAIL (-5.7) | FAIL (-10.3) |

**Book readout** (#463 with the sized #234, on the book's walk-forward window 2016-07-13..2025-06-29): WF ROC
84.4 against #463's 94.0, Sortino 3.65 against 3.88, and $39,909 behind by calendar year. **FAIL.**

Sized #314 in the seat reads 107.4, above 94.0 but below the 125.6 that raw #314 gives (Frontier run #473).
The tilt makes that seat worse too.

## What the thirds show (reported, never judged)

Walk-forward dollars per trade by the breakout bar's relative volume:

| | bottom third | middle third | top third |
|---|---|---|---|
| #314 | $258 (PF 1.44) | **$325 (PF 1.63)** | $126 (PF 1.18) |
| #234 | $192 (PF 1.30) | **$377 (PF 1.70)** | $50 (PF 1.07) |

- **The ordering the pre-registration predicted (top above middle above bottom) is wrong.** The heaviest
  breakout bars are the WEAKEST third on both crowns, and the middle third is the best.
- The plausible reading is the opposite mechanism: a climax bar that spends the move. But the top-minus-bottom
  gap is under one standard error (#314 -$132, SE $172; #234 -$142, SE $155). **It does not license an inverse
  tilt.** Proposing one now would be choosing a rule after seeing these numbers, which is exactly what the
  pre-registration exists to prevent.
- RVOL is unrelated to the opening-range width (rank correlation -0.03 / -0.005), so this was new information.
  It is just not useful information.
- Skipping the bottom third (reported, never adopted) gives WF ROC 28.6 for #314 and 34.2 for #234, at or below
  the raw crowns. That is consistent with filters failing every time.
- The 2010-06..2016-07 block, untuned for the tilt, agrees: #314 0.6 to -0.7, #234 -0.2 to -0.3.

## What this closes

- Breakout-bar volume, in any form (gate, tilt, rank), on the legal close-confirmed ORB: **DEAD. Do not re-test**,
  and do not run the inverse tilt. Together with the 08-10 audit, the "high-volume breakouts work" folklore is now
  dead on ORB twice.
- The **order-flow forward shadow** reads the same bar's 10-second delta. This round says volume did not carry
  the edge, so expect little from delta; that test stays forward-only and keeps its own pre-registered rule.
- **Roll week** (#314 PF 2.14 on 97 trades, seen by accident in the smoke run and disclosed) stays a forward read
  or its own pre-registered calendar test with a family-aware null. It is not proposed here.
