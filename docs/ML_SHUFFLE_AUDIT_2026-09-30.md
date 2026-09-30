# ML SHUFFLE AUDIT — do the sized book legs aim, or only shape? (2026-09-30)

Bar written and pushed BEFORE running tools/ml_shuffle_audit.py. Lesson that prompted it: TTM #458 KEEL's
walk-forward win sat at the 76th percentile of its own sizes shuffled (docs/PREREG_fixed_sizing_r1_2026-09-28.md).
ROC at a $30k drawdown already removes plain leverage; the shuffle also removes the SHAPE of the sizes (a
spread of big and small sizes changes the drawdown path by itself), so what is left is aim.

- Legs: every sized export in C:\EdgeLog\book_legs (NOISE #422 fixed / KEEL s42 / KEEL bag7, NOISE #382 KEEL s42 /
  fixed, ORB #314 tree HYBRID DD, ENGU-Q #335 and #335-paper rf HYBRID DD, TTM #368 and #458 KEEL) vs its raw twin.
- Null: the arm's own per-trade multipliers shuffled across the same trades, 1,000 times, seed 20260930.
- AIM SHOWN = the arm's ROC %/yr at a $30k worst drawdown is above the 95th percentile of its shuffles, read in
  WF and LB separately. Below that, the leg's gain over raw is not distinguishable from its size shape.
- This is an audit of legs already judged; it changes nothing live. Legs showing no aim in WF are flagged to
  their lanes and to Frontier (book-leg streams); no rerun or retune follows from it.

## RESULT (run once, as registered) - no sized leg shows aim in BOTH stretches
Shuffle percentile of the arm's ROC %/yr at a $30k drawdown (raw -> arm in brackets); 95 = aim shown.

| leg | WF pct (raw -> arm) | LB pct (raw -> arm) | aim shown? |
|---|---|---|---|
| NOISE #382 fixed tilts | **98.0** (80.2 -> 93.8) | 92.6 (70.1 -> 94.2) | WF only |
| NOISE #422 fixed tilts | 94.8 (84.7 -> 109.1) | 90.6 (94.7 -> 126.6) | no (both just under) |
| NOISE #382 KEEL s42 | 90.4 (80.2 -> 78.2) | **95.6** (70.1 -> 117.2) | LB only |
| NOISE #422 KEEL s42 | 65.7 (84.7 -> 78.0) | 83.6 (94.7 -> 127.6) | no |
| NOISE #422 KEEL 7-seed bag | 69.3 (84.7 -> 79.4) | 83.1 (94.7 -> 124.8) | no |
| ORB #314 tree HYBRID DD | 93.8 (35.3 -> 42.3) | 92.8 (114.7 -> 134.4) | no (both just under) |
| ENGU-Q #335 rf HYBRID DD * | **98.3** (24.1 -> 47.3) | 49.9 (35.3 -> 35.7) | WF only |
| ENGU-Q #335-paper rf HYBRID DD * | 40.8 (34.1 -> 28.5) | 1.4 (58.4 -> -11.7) | no - aims WRONG in LB |
| TTM #368 KEEL | 93.8 (56.7 -> 70.6) | 90.2 (16 LB trades) | no |
| TTM #458 KEEL | 77.3 (29.5 -> 33.4) | 60.4 (12 LB trades) | no |
\* ENGU-Q holds for weeks; entry-day drawdowns are understated for both arms.

- **Reading:** every learned sizing (KEEL, tree, rf) is at or below the shuffle bar in at least one stretch; the
  WF-only passes (ENGU-Q rf, #382 fixed tilts) sit on stretches their settings were chosen on, so they are not
  clean. The fixed NOISE tilts come closest in both stretches (94-98 / 91-93) - the same "simple fixed rules
  beat learned models" pattern as every earlier round, and still not proof.
- **Consequence:** nothing live changes. The forward shadows already running (NOISE arms, ORB tree, TTM KEEL)
  remain the only test that can settle aim; this audit sets expectations low for the learned ones.
