# NOISE TARGET r1 - ADDENDUM 1: a POST-DATA parity fix to the harness, disclosed (2026-10-12)

**What run 1 got wrong.**
- The harness read each leg's squeeze gate (which sets the size, 1.75x or 2.0x) on the RAW NQ prices.
- Since the 10-08 roll guard, the engine hands strategies a ratio-adjusted series, and NOISE_1_8_CT304 / CT304H read the
  gate on that series.
- Run 1's parity check compared entries and exits only. It missed 9 (#422) and 14 (#382) walk-forward trades sized
  differently from the engine.
- Those 9 trades sit inside #422's worst drawdown (2025-03-14 .. 2025-06-20). They moved its base ROC@30k from 83.2 (the
  engine's sizes) to 73.3.

**The fix.**
- The harness now captures the exact arrays the engine passes the strategy, and reads the gate on them.
- Parity now also asserts that every trade's size equals the engine's own trade_sizes, for both legs, before any cell runs.

**Not changed:** the cells, levels, fill rules, costs, stretch and bars are exactly the prereg's.

**Disclosed:** run 1's numbers were seen before this fix. They move the bases, not the cells' rules. Run 1's output is kept
as `noise_target_r1_stageA_run1.txt`.
