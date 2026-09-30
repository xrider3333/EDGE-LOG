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
