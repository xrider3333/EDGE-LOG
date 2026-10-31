# PREREG addendum - test 75, ORB half (ORB #126): the two ORB details the shared prereg leaves open

`docs/PREREG_noise_orb_t75_scaleout_2026-10-31.md` (28885f3c) is followed unchanged. Written and pushed BEFORE any ORB
scale-out is simulated. Only these two points were undefined for ORB:

1. **Fixed triggers {2, 4, 6} in the live instrument's points.** ORB #314's live leg trades QQQ on Webull, so the live
   points are QQQ $/share, translated to the NQ WF chain as a % of entry at the SAME 10-30 reference the prereg gives NOISE
   (QQQ 690): 2 = 0.290%, 4 = 0.580%, 6 = 0.870% of the entry price.
2. **The chain and R.** ORB #314's WF chain is the test 74 rebuild (`tools/orb_t74_giveback.py`, 8 anchored folds
   2016-07-13 .. 2025-08-12, per-fold stored params, NQ 5m `db_noadj_rth`, 0.533 pts a round trip, one contract x $20;
   7/8 folds bit-exact, fold 4 differs by the two 2020 splices). R = the entry's own protective-stop distance
   (`levels[].risk`). The leg's own breakeven-after-0.5R stays part of HOLD and of every remainder; the BE-on arm only adds
   the prereg's move-to-entry after the scale bar. Extra exit cost = 0.533 / 2 x F.

Everything else (30 cells, stop-first rule, reading rule, MFE captured, lockbox never loaded) is the shared prereg's.
