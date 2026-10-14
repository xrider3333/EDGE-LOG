# PREREG - NOISE TARGET r1, OWNER OVERRIDE 10-12 (MANAGER #89): run T25 / SO25 / T100 on #422 and #382

**OWNER OVERRIDE 10-12, recorded (MANAGER #89):** "what was the roc/yr on those tested. Keep testing them." The owner overrides the
power-first gate for these three cells only (MANAGER #88 had closed them at draft). Frozen before any target trade is simulated;
pushed as the witness branch prereg/noise-target-1012 with its LF sha256 and the harness's posted to MANAGER before the run (rule
#77). Harness: `tools/noise_target_r1_stageA.py` (it refuses unless this file's LF hash matches its pin). Walk-forward only; the
lockbox is not read. Nothing live or in the book changes; any verdict is a report to MANAGER.

The draft below is unchanged from the version MANAGER reviewed (#919, sha e17aa3f9). Its gate verdict stands as the prior.

---

# DRAFT - NOISE TARGET r1: can a profit target buy NOISE a higher win rate without cutting ROC? (owner order 10-12, MANAGER #86)

Drafted 2026-10-12 by the NOISE lane, after the scatter report (`noise_scatter_r1.txt`, `noise_scatter_r1.png`, this folder).
NO target has been simulated. Disclosed: the cells below were written after the scatter's MFE table was seen. Their levels are
the house's own conventions (round 37's 1R; a quarter-R scalp), chosen before any capped P&L was computed.

## What the scatter says (WF 2016-07 .. 2025-06, 2,803 trades shared by #382 and #422, cost 0.783 = commission + one tick a side)

**Four numbers per leg:**

| Leg | ROC@30k | DD5 | DD% | Sortino | Win rate | Avg win / avg loss |
|---|---|---|---|---|---|---|
| NOISE #422 | 82.9 | $13.0k (one episode) | 7.0% | 4.12 | 36.8% | 2.54x |
| NOISE #382 | 78.1 | $18.2k | 9.8% | 3.53 | 36.8% | 2.49x |

At the house cost of 0.533, #422 reads 87.6 and #382 82.0.

**A right-tail strategy:**
- The top 50 trades (1.8%) make 87% of net; the top 100 make 141%.
- Trades held 4 hours or more make 229% of net. Every bucket under 60 minutes loses.

**MFE in R (R = entry to the initial stop, median 62.7 pt):**
- 47% of trades never get 0.25R in their favour; they win only 14% of the time.
- Trades that reach 1R or more are 21% of trades and make 257% of net. Most of them are held to the close.

**Giveback is small:**
- VWAP exits that ran 1R or more and still closed at a loss: 69 trades, -$17.5k over nine years.
- At 0.5R the count is 282 trades, -$85k.

**The structural answer:**
- No target at 0.5R or above can lift the win rate much. The win rate is already about the share of trades that reach
  0.5R (36.8%).
- Only targets under about 0.25R lift it (toward 50-55%), and those cap the 21% of trades that carry the net.
- **A higher win rate on NOISE is the trap MANAGER named: small wins, the same losses.**

## Cells (if GO)

Every cell is the #304 core entries unchanged, with each leg's own size rule.

- **T25, the scalp:** a resting limit at +0.25R.
- **SO25:** half the position off at +0.25R; the other half rides NOISE's normal exit.
- **T100:** a resting limit at +1R (round 37's convention).

Shared rules for all three:
- **Fills:** the target fills on the touch, inside the bar. If a bar touches both the stop and the target, the stop
  fills first. The entry bar is not checked (the engine's own stop rule).
- **Re-entry:** after a target exit, the position slot is free for the next break, as after any exit.
- **Stretch and parity:** walk-forward only, lockbox unread. The variant first rebuilds #382 and #422 trade for trade at
  target = off.

**Bars (per leg, cost 0.783):**
- Beat the leg's own walk-forward ROC@30k AND Sortino.
- Month-block bootstrap P(delta ROC > 0) of at least 0.90.
- Print the four numbers, the win rate and avg win / avg loss.
- A pass needs its neighbour cell (T25 vs SO25, T100 vs 2R) to stay positive.

**Power line:**
- #422's own walk-forward ROC has a month-block bootstrap SD of 25.6 (5-95% band 45 .. 131); Sortino SD 0.71.
- The paired delta is tighter than that, but a one-episode drawdown sets the yardstick. A real gain of under about 10
  ROC points cannot be told from noise.

**Prior, written now:**

| Cell | Effect on win rate | ROC change | P(pass) |
|---|---|---|---|
| T25 | up to about 50-55% | down by more than 40 | about 0 |
| SO25 | about half of T25's rise | down about 20 | under 5% |
| T100 | up 1-2 points only | -10 .. +5 | about 15% |

None of these clears the gate as an improvement. T100 does not lift the win rate, so it is a plain exit refit in a space
rounds 52, 65 and 68 closed ("exits stay closed for this family").

**Gate verdict: T25 and SO25 close at draft (the win-rate trap). T100 is a refit of a closed space.**
If the owner wants the scalp on the record anyway, the three-cell triage costs about an hour after GO. The rule #77
witness branch and the hashes come first.
