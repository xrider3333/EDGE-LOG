# PREREG - SUPERSCALPER r2b: the outside-RTH / RTH split on 2023 (OUR PORT, development data only) - TV, 2026-10-15

MANAGER #135 (after r2 E1): "the money is OUTSIDE RTH (2024: 2,009 trades, PF 1.085) while every RTH window loses - pre-register and
run the same outside-RTH split on 2023 (dev, already spent by E0) - does overnight carry it there too?" Written before any 2023
split number. 2023 was read as a whole in r2 E0 (both exits ~1.07 net PF); its split was not.

## Fixed
- Same port, engine, master, cost and four-number helper as r2 (prereg/tv-ssexplore-1015, docs/PREREG_tv_superscalper_r2_explore_
  2026-10-15.md): port LF sha 8566c2c1..., NQ 1m ETH no-adjust id 34, intrabar 'worst', cost 0.706, file defaults (IMPROVED_R1).
- The harness `tools/superscalper_explore_r2b.py` imports r2's harness (LF sha 26a2f9aa..., checked) for its runner and readers.
- Decomposition exactly as r2 E1: close_rule 'any', each trade tagged by its SIGNAL bar's New York time; RTH = 09:30-15:59 ET
  (W1 + W2 + W3), outside RTH = everything else (W4).
- One read: NQ 2023-01-01 .. 2023-12-31, file defaults. Printed: all / RTH / outside RTH, and W1 / W2 / W3 for information.

## Reading (fixed now)
- "OVERNIGHT CARRIES 2023 TOO" if outside-RTH net PF >= 1.00 AND outside-RTH net PF > RTH net PF. Otherwise "it does not".
- Either way this round adds NO filter by hand. MANAGER #135 (b): a session knob (all / outside RTH only / RTH only) goes into the
  validate file's search space under its own prereg amendment, so the 900-trial search finds or rejects it on the walk-forward.
