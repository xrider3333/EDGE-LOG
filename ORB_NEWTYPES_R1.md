# ORB lane NEW STRATEGY TYPES r1 — NT1 MACRO830 and NT3 SAFEHAVEN: both DEAD at Stage A (2026-10-07)

Pre-registration: `docs/PREREG_orb_newtypes_r1_2026-10-05.md`, on main at 01bd1a9f before any number, with MANAGER's review
folded in as addendum 1. TV's read-only mistake hunt on both tools (inbox #44) found no defect. NT2 ANNPREM was dropped on
the map before it ran.

Tools: `tools/orb_nt_common.py`, `orb_nt1_macro830.py`, `orb_nt3_safehaven.py`. Walk-forward 2016-07-01..2025-06-29 only;
the lockbox is untouched.

**Parity.** #463 reproduces exactly (93.81 / 3.816 / $44,849) from the house valued-daily cache
`rocfrontier/r4/book463_daily.csv` (sha256 d1543735...). The drawdown-day count is 460, the same as TV's.
- First run, disclosed: my own rebuild of #463 from the book engine's leg rows gave Sortino 3.881, because it carries
  only days that have a leg row. The tool stopped on its parity check before any cell was scored. It now reads the
  house cache that every drawdown-week lane uses.
- Report-only lines were added after the prereg and before the run, as the 10-07 DD5 rule and the 10-05 "deeper per
  test" order require. They change no bar: DD5, regime halves, long vs short, cost curve.
- The book add (k) is a REPORT, not a gate (house line, MANAGER #40 / #45).

## NT1 MACRO830 — carry the 08:30 CPI / payroll reaction into the cash open: DEAD (0 of 4 cells)

Continuation LOSES on every cell: NQ every release day -$41,544 over 210 walk-forward trades (PF 0.67, t -1.98, ROC @ $30k
-3.0, DD $46,697, DD5 $9,768); ES -$23,636 (t -1.99). It loses before costs too (NQ gross -$39,305), in both regime halves,
in 2010-16, and without 2020 or 2022. The "big move" cells are no better.

**The reaction partly REVERSES into the cash open.** The fade mirror (reported, never a pass route) earns NQ +$37,066
(mean $177, t 1.77) and ES +$16,014 (t 1.35). Both are below the null's 95th percentile (1.98).

The prereg's mechanism (an incomplete pre-open adjustment that the cash open finishes) is wrong in sign. The losses sit
mostly on the SHORT side (NQ shorts -$37,399 of the -$41,544). So bad-news drops recover into the open more than good-news
pops do.

**A fade is NOT proposed from this.** It was seen here, its t is under the null, and it would be a new pre-registration,
judged forward.

## NT3 SAFEHAVEN — long IEF / GLD 10:35 -> close on equity-stress mornings: DEAD (0 of 4 cells)

On mornings when ES is already down k x its usual move by 10:30, both funds LOSE over the rest of the day:
- IEF k = 2 (the mechanism's test): 244 trades, -$19,628 (PF 0.43, t -4.40, DD $19,797);
- GLD k = 2: 245 trades, -$26,736 (PF 0.52, t -3.48);
- the k = 1 dilution cells are the same.

Both lose before costs (IEF -$9,868, GLD -$16,936 gross), in both regime halves, and in 8 or 9 of 9 years. They make
nothing on #463's drawdown days (IEF -$8,631; GLD -$234 against a null 95th percentile of $4,439).

The flight to safety, where it happens, is already in the price by 10:30, and the rest of the session gives it back. The
named enemies played their part but are not the story: the 2020 dash for cash cost IEF -$3,493 over 5 trades, and 2022
was about flat. The loss is everywhere.

## What this closes

- Scheduled macro releases on NQ/ES are dead as a continuation trade into the open. The event-size scan already made
  them noise as size rules on existing legs.
- Intraday flight to quality in IEF/GLD on equity-stress mornings is dead.
- The fade-the-release reading and the "safe havens give back the morning" reading are both post-hoc observations. Each
  needs its own pre-registration and a forward read; neither is drafted here.
- DD5 note: every NT cell's curve is a steady loss, so the worst drawdown dwarfs DD5 or there is a single episode (n = 1).
  The ROC figures are negative either way; DD5 changes nothing.
