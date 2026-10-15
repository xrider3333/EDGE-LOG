# PREREG - SUPERSCALPER r2 EXPLORE (OUR PORT, development data only) - TV, 2026-10-15

Owner 10-15 via MANAGER #133: "keep exploring the scalper" while the 900-trial Auto-Validate waits for TBIS's runner restart.
Development data ONLY: 2024 (already spent by r1) and 2023 as a second development year (unread until this round). No other
walk-forward year and nothing from the lockbox (2025-06-30 ..) is read. Written before any number of this round.

## What is fixed
- Port: `augur_strategies/MISC_SUPERSCALPER_1_0.py`, LF sha256 8566c2c14e68291807e79854c040cf2ad156006f6b47a7e637f4eca5240fe918
  (the r1 file: defaults = IMPROVED_R1 = target x2.0, breakeven at +1.0 R, daily VIX, cap off, stop x1.0, no time-out;
  AS_PORTED_OURS = the script's own exits). Read from the session/superscalp worktree until it lands on main.
- Engine and masters from the shared checkout: NQ 1m ETH no-adjust id 34 (NOADJ_NQ_1m_ETH.csv), ES 1m ETH no-adjust id 30
  (NOADJ_ES_1m_ETH.csv). intrabar 'worst'. VIX = the raw CBOE photograph (sha 6edc3e39..., the port default).
- Cost (owner rule: commission + 1 tick each side): NQ 0.706 pt ($14.12); ES 0.582 pt (same $4.12 commission + 2 x $12.50
  = $29.12 / $50). Stress line +0.25 pt.
- Four numbers per result (house helper pattern, tools/orb_relay_r1.py four()): ROC %/yr at a $30k worst drawdown (daily P&L by
  exit date, 1 contract: NQ $20 / ES $50 a point), DD5 and DD % from peak at that $30k sizing, Sortino (daily, x sqrt 252); plus
  trades, win rate, average win / loss (net points), net PF, net points.
- Harness `tools/superscalper_explore_r2.py` checks this file's LF sha and the port's sha at start and refuses on a mismatch.

## E0 - the r1 pick on the second development year (the selection-luck check)
STRATEGY-BEATING #127: the r1 pick (net PF 1.051) is inside what picking the best of 216 cells produces by luck alone. One read:
NQ 2023-01-01 .. 2023-12-31, file defaults (IMPROVED_R1) and AS_PORTED_OURS side by side.
- HOLDS if the IMPROVED_R1 2023 net PF >= 1.00 AND it beats the as-ported 2023 net PF. Otherwise: "r1 pick does not hold on
  2023" is reported to MANAGER before the validate is queued (the validate still runs - owner order - but the read is labelled).

## E1 - time-of-day windows (NQ, 2024 then 2023)
A DECOMPOSITION of the file-default run, not new strategies. Every trade is tagged by its SIGNAL bar's New York time; the run uses
close_rule 'any' (each bracket closes its own ticket - same total points as 'fifo', per-trade rows differ; the harness prints both
totals as a check). Windows (ET, signal bar): W1 RTH open 09:30-10:59, W2 midday 11:00-13:59, W3 RTH close 14:00-15:59, W4 outside
RTH (16:00-09:29).
- A window is a CANDIDATE if its 2024 net PF >= 1.10 with >= 300 trades.
- Candidates (only) are read on 2023 once. CONFIRMED if 2023 net PF >= 1.05 AND 2023 ROC@30k >= 15 (the MDL map line).
- A confirmed window becomes a written proposal for an entry-window knob in a LATER prereg (never added to the queued validate).
- Power, stated first: ~650 trades a window, per-trade SD ~35 pt -> a window's net PF has a sampling SD of ~0.09; the 2024
  candidate rule alone is close to noise, the 2023 confirmation carries the test. P(confirm | true PF 1.10) ~ 0.7; P(confirm |
  true PF 0.95) ~ 0.13. Prior that some window is a real lift of >= 0.1 PF: moderate (open/close volatility differs from midday).

## E2 - the same port on ES (2024)
Three cells, 2024 only: (a) AS_PORTED_OURS, (b) file defaults (IMPROVED_R1), (c) file defaults with the three NQ-point knobs
scaled x0.25 for ES's price level (tp_buffer 1.0 -> 0.25, min_profit 5.0 -> 1.25, min_atr_pts 5.0 -> 1.25; 0.25 = the rough
ES/NQ price ratio, fixed now, not fitted). The port reads ES / QQQ helper feeds only on NQ, so on ES those votes take the script's
own missing-data branch (stated, not repaired).
- A cell is a CANDIDATE if its 2024 net PF >= 1.05 with >= 500 trades; the best candidate (highest net PF) is read once on ES 2023:
  CONFIRMED if 2023 net PF >= 1.00 AND ROC@30k >= 15. A confirmed ES cell = a written proposal for its own Auto-Validate (later prereg).

## What is different from the 10-12 scalp hunt (0 of 59 on 1-minute)
That hunt tested simple single-rule 1-minute scalps; none reached ROC 15 on walk-forward. This is a six-path confluence design whose
r1 exits turned a 0.96 dev-year net PF into 1.05 - thin, and possibly selection luck (E0 asks exactly that on an unread year).

## Not done here
No change to the queued validate's file, ranges or window. No lockbox. No third development year. The validate's walk-forward read
will print the folds overlapping 2023 AND 2024 apart, plus the chain without them, because both years are now development years.
