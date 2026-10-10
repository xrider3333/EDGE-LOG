# BVC QA r1 - RESULT (TV, 2026-10-10)

Prereg: `docs/PREREG_tv_bvcqa_2026-10-10.md` (witness branch prereg/tv-bvcqa-1010 @ 1a1f87bc, LF sha256 d7438899...).
Harness: `tools/tv_bvcqa_r1.py` (LF sha256 df19e818..., posted to MANAGER before the run). Output: `tools/data/tv_bvcqa_r1.txt`.
Data QA only: no P&L, no strategy, no lockbox.

## Verdict as registered: FAIL
THE STATISTIC, pooled r(BVC, real delta) over NQ 1-minute bars, = **0.137** against the 0.60 bar. Kept: 25 NQ sessions
(2026-06-30 .. 10-07, 9,673 bars), 31 ES. Reported beside it: ES 1-min 0.554; NQ 5-min 0.316; ES 5-min 0.558; median per-session r
NQ 0.592, ES 0.463; price change alone r(dP, D) NQ 0.587, ES 0.484.

## Why it failed: the TRUTH series, not the proxy (diagnostics after the number - none is a pass route)
1. **Delta drops while rt = 1.** 8 of the 25 kept NQ sessions (10 of 31 ES) carry delta = 0 on more than half their 1-minute bars
   although every row is flagged live: NQ 08-18, 08-24, 08-27, 08-28, 09-01, 09-02, 09-22, 09-25 (ES adds 08-20, 09-10, 09-14,
   09-17). The prereg's live-share filter could not see this - the rt flag says live, the delta column says nothing.
2. **Impossible volume rows.** Two NQ minutes on 2026-09-24 (13:01 with 413,667 contracts, 13:30 with 449,708 - about 500x the median
   minute) and one ES minute (2026-06-30 15:59, 133,661). One of them alone dominates a pooled Pearson.
3. On the 17 NQ sessions with delta present and the spike bars out: r(BVC, D) 0.653 - but **r(price change alone, D) 0.670**.
   ES: 0.586 vs 0.557. BVC adds nothing over the bar's own price change.

## Reading (per the prereg, plus what the diagnostics add)
- Closed. Order flow stays forward-only on the NT capture.
- No r2: even on clean sessions the price-only proxy is the price change by another name, so a 15-year "delta" built from bars
  would carry only price information the house has already mined. What makes real delta worth having is the part price can't
  explain (about 55% of its variance on clean NQ sessions), and that part exists only in the live capture.
- **Capture QA finding (for the owners of the 10s capture and of the NOISE order-flow shadow):** zero-delta sessions with rt = 1 are
  still occurring (09-22, 09-25), and the file holds impossible-volume rows. Any delta reading should first drop sessions whose
  delta is zero on most bars, and bars with volume far above the session's normal.
- Harness note: the per-market header line "duplicate time rows dropped" is mislabelled - it counts the non-RTH rows filtered out
  (the files hold no duplicate times; checked). Cosmetic; no statistic uses it.
