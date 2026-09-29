# PRE-REGISTRATION — forward test of the NOISE sizing arms on the live Webull paper fills (2026-09-28)

Committed before the first shadow trade is scored. Nothing below changes once scoring starts; anything
learned afterwards goes in a POST-HOC section.

## Why
Owner decision 2026-09-28 (via MANAGER inbox #21): the live Webull NOISE primary stays **#382 + KEEL v12**;
Paper: WB adds #422 plain, #422 + fixed tilts and #422 + KEEL as background shadow legs. Every tilt and KEEL
setting was chosen reading NOISE #243/#304's walk-forward AND lockbox through 2026-08-12, and the only clean
data since (27 trades, docs/PREREG_keel_422_parts_2026-09-27.md POST-HOC) cannot separate the arms. Only
forward trades can.

## The arms (same signals, same fills - only the SIZE differs)
NOISE #382 and #422 are both run #304's signal stream re-sized, so every arm trades the same entries and exits.
Each forward trade's P&L per arm = the primary's ACTUAL per-share fill P&L x that arm's size multiplier m.
Execution therefore cannot decide the test.

| arm | m (multiplier on one base unit) |
|---|---|
| P  primary | #382 plain x KEEL v12 on the #382 base (the live leg) |
| A1 #382 plain | 2.0 when #382's 30-min squeeze (16 / 1.15) is on, else 1.0 |
| A2 #422 plain | 1.75 when #422's hourly squeeze (20 / 1.15) is on, else 1.0 |
| A3 #422 + fixed tilts | A2 x compression 1.5 x Friday 1.5 (product capped 3.0) x FOMC-morning 0.5 - exactly ml_keel.compression_sizes(mult=1.5, dow={'4':1.5}, cap=3.0, event={'mult':0.5,'cut_hour':14}) |
| A4 #422 + KEEL | A2 x KEEL v12 on the #422 base (seed 42, same nightly refit as the primary) |

Scored on the UNCAPPED multiplier so the per-leg share caps cannot favour one arm; the capped share P&L is
reported beside it. If a shadow arm's signal ever differs from the primary's, that trade is logged and
scored for that arm at its same-day backtest-replay fill, and counted in the report.

## The yardstick (owner rule 2026-09-28, one for every lane)
- **ROC %/yr at a $30k worst drawdown** = 30 x (annualised net / max drawdown), drawdown valued daily (NOISE
  is flat by the close, so daily = realised).
- **Sortino**: augur_engine.analytics.sortino_from_pnls on per-trade $, annualised.
- **Fragility**: net must stay positive without the arm's single biggest trade.

## Questions and decision rules
- **Q1, does a sizing layer earn its keep?** Each sized arm against its own raw twin: P vs A1, A3 vs A2,
  A4 vs A2. The layer earns its keep only if it beats the twin on ROC-at-$30k-drawdown AND on Sortino AND
  passes the fragility check.
- **Q2, should the primary change?** Each arm against P on the same two numbers. An arm "beats the primary"
  only if it wins on both and passes the fragility check.
- **Minimum 100 forward trades before any verdict** (the owner's walk-forward minimum). Verdict at 150
  trades or 2027-03-31, whichever comes first. Reads before 100 trades are informational only.
- Nothing live changes on this test's say-so; a pass is an owner decision via MANAGER.

## Window and data rules
- Starts with the first primary trade entered after Paper: WB confirms the shadow logging is live (that
  date is recorded in the first scoring report).
- Trades the primary did NOT fill (rejection, halt, dead-man stop) are scored for every arm at the
  backtest-replay fill and listed separately; no trade is silently dropped.
- QQQ has no contract roll; KEEL's NQ training master does (December 2026). Roll week is flagged in the report.
- Scoring: the Custom ML chat, from Paper: WB's log plus a same-day backtest replay as a cross-check.

## ADDENDUM 2026-09-29 (owner YES, MANAGER #27) - before any forward trade was read
A paired sequential early stop now runs beside the final rule above, which is unchanged:
docs/PREREG_paired_sequential_stop_2026-09-29.md (scorer tools/paired_seq_stop.py).
