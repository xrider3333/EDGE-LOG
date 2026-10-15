# PREREG - SUPERSCALPER r2c: which RTH hours carry it, and does it survive +1 tick (OUR PORT, development data only) - TV, 2026-10-15

MANAGER 13:10 (owner 10-15 "keep exploring the scalper", while the validate waits on TBIS's runner restart): "(a) which hours carry
the RTH edge (PF 1.21 vs 1.02 outside), split 09:30-10:30 / midday / 15:00-16:00; (b) does it survive cost +1 tick." Written before
any number of this split. DESCRIPTIVE ONLY: no candidate, no filter, no adoption - the only session choice the house will act on is
the validate's own `session_filter` search (prereg Amendment 5 on the r1 prereg).

## Disclosure (what is already known)
r2 E1 (2024) and r2b (2023) printed W1 09:30-10:59 / W2 11:00-13:59 / W3 14:00-15:59: 2024 = 0.968 / 0.939 / 0.956 (all RTH lost);
2023 = 1.477 / 0.949 / 1.145 (RTH carried). The new cut overlaps those windows; it is a re-cut of seen data, read as description.

## Fixed
- Port: `augur_strategies/MISC_SUPERSCALPER_1_0.py`, LF sha256 b8ef032f89c1adb1a57093df0a319060a9c2165ff6565c09c2a90f0d6a2955e1 (the r1
  file + the Amendment 5 session knob, default 'all' = the r2 / r2b port's trades). PARITY GATE first: the harness reproduces r2b's
  2023 decomposition total (2,311 trades, 2,005.9 net points at 0.706) with this file; it refuses to print the split otherwise.
- Engine, master (NQ 1m ETH no-adjust id 34), intrabar 'worst', file defaults (IMPROVED_R1, session all), close_rule 'any'
  decomposition tagged at the SIGNAL bar (New York time), four-number helper: all from r2's harness (tools/superscalper_explore_r2.py,
  LF sha 26a2f9aa..., on main), imported and sha-checked.
- RTH sub-windows: H1 09:30-10:29, H2 10:30-14:59, H3 15:00-15:59 (signal bar). Years: 2023 AND 2024 (both already development years;
  nothing else read).
- Costs: 0.706 pt (owner rule) and 0.956 pt (+1 tick = +0.25 pt). Each window printed at both, with the four numbers (ROC@30k, DD5
  and DD% from peak at the $30k sizing, daily Sortino), trades, win rate, average win / loss, net PF, net points.

## Reading (fixed now)
- "An hour carries it" only if its net PF >= 1.10 in BOTH years with >= 100 trades in each; reported, never acted on here.
- "Survives +1 tick" per window/year = net PF > 1.00 at 0.956.
