# ORB round 63 — which ORB leg should BOOK #463 carry? (2026-09-30)

Pre-registered in `tools/orb_r63_book463_orb_leg.py` (6850d17a) before any number. Only #463's ORB leg
changes; every other leg is #463's own, read from its job document, with daily-valued series from the
house book engine. **Parity exact:** the stored legs reproduce #463 to the cent (pre-lockbox
$1,358,771.79, lockbox $273,608.73). Output: `_r63_book463_orb_leg.log`.

Stretches: walk-forward-like 2016-07-13 → 2025-06-29; lockbox 2025-06-30 → 2026-06-30 (#463's own, already
read when the book was adopted, so a veto rather than evidence). ROC at a $30k worst drawdown, drawdown
valued daily.

| ORB leg in #463 | WF ROC@$30k | WF Sortino | WF daily DD | LB ROC@$30k | LB Sortino | vs #234 by calendar year | Bar |
|---|---:|---:|---:|---:|---:|---:|---|
| **#234 (incumbent)** | 94.0 | 3.88 | $44,849 | 155.5 | 4.22 | — | — |
| #314 (crown) | **125.7** | 4.02 | **$33,735** | 147.3 | 4.02 | +$16,680 (9/15) | FAIL — lockbox lower |
| #257 (money pick) | 108.7 | 3.99 | $39,917 | 146.3 | 3.96 | +$34,408 (9/15) | FAIL — lockbox lower |
| **#239 (breakeven 0.8)** | 101.9 | 3.90 | $41,319 | **158.7** | **4.31** | +$1,235 (8/15) | **PASS** |

## Reading it

- **#239 clears the pre-registered bar, narrowly.** It beats #234 on ROC at $30k and on Sortino in both
  stretches and is not behind by calendar year. The size of the gain is small: +7.9 points in the
  walk-forward years (almost all of it a $3.5k shallower drawdown), +3.2 points in the lockbox, and
  +$1,235 over fifteen calendar years. Under the pre-registration that is a **recommendation for an owner
  call**, not an adoption.
- **#314 is the most interesting number in the table and does not pass.** Inside the book it cuts the
  walk-forward drawdown by $11,114 and lifts walk-forward ROC at $30k from 94 to 126%/yr, but it earns
  $13,643 less in the book's lockbox year, and the lockbox is the veto. The book's lockbox drawdown
  ($49,855) is ENGU-Q's in every variant, so the lockbox ROC column is money only.
- **#257 earns the most by calendar year and still fails**: better walk-forward, weaker lockbox.
- Caveats: three swaps were compared on data the ORB configurations were chosen on; the lockbox has been
  read before; and #239 is a pinned card whose own walk-forward is an in-sample read. The owner decided on
  2026-09-28 that #239 is not a swap for the ORB *crown*; this is a different question (the book's ORB
  leg), so it goes back to the owner rather than being inferred from that.

## Recommendation

Per the pre-registered bar: **offer the owner the #234 → #239 swap in BOOK #463's ORB leg as a small,
low-stakes improvement** (same entries as #234; only the breakeven trigger moves from 1.0 to 0.8 of the
risk). The ORB lane would not push for it hard: the gain is mostly a slightly shallower drawdown and is
within what one parameter step can manufacture. Book composition belongs to the Frontier lane.
