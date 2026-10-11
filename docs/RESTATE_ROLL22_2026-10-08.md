# RESTATE - the 22 old-roll-detector runs on the TRUE roll table (DISC for MANAGER #59 / #60 / #62, 2026-10-08)

**Report only.** Same file, same settings (the validate's champion), same window, same cost. Nothing re-tuned and no validate re-run, so the verdicts are not restated. Money is $ on the run's own multiplier. ROC = 30 x (net / years) / worst drawdown on the daily curve booked on exit days. DD5 = mean of the 5 worst drawdowns. (1 ep) = worst DD > 1.3 x DD5.

## Method

- **Parity first.** Each run was re-run from its stored settings. All 22 match their stored ungated pre-window and lockbox totals (trades and P&L) exactly. The 12 runs that store a full-window total also match it exactly.
- **DIP (NQDIP 1.0 / 1.1), PURE line (MANAGER #62).** The true-roll twin (1.2 / 1.3) with two exact source edits that put back 1.x's rule: no entry and no exit fill on a roll session. The roll sessions are now the TRUE ones. The only change from the saved file is the roll handling: the true contract offset leaves the P&L, and every real gap stays in. The twin itself (roll-day fills allowed) is shown alongside.
- **TTIBS / GAPGO / RSIDIV (no twin).** The file runs unchanged, except that its own `detect_roll_seams` returns the TRUE switch sessions from `tools/data/rolls_NQ.csv`. It therefore flattens before, and skips, the real roll days instead of the detector's guesses. That is pure by construction.
  - Control: the same patch returning the detector's own answer reproduces every saved run exactly.
- **LB here = the lockbox year sliced from the continuous run** (how `gate_validate.ungated_lockbox` is built). The validate's fresh-start lockbox strip is not restated.
  - #163's September 2025 roll error sits only in that strip. It is not in the continuous run.

## Results (FULL = the run's whole window; saved -> true)

| run | file | net $ | worst DD $ | DD5 $ | ROC@30k | pre-window ROC | LB net $ | LB ROC |
|---|---|---|---|---|---|---|---|---|
| #161 VOID | TTIBS_1_0 | 422,293 -> 416,397 | 43,531 -> 47,617 (1 ep) | 32,454 -> 31,804 | 18.1 -> **16.3** | 15.9 -> 14.3 | 86,301 -> 86,301 | 46.1 -> 46.1 |
| #163 | RSIDIV_1_0 | 1,674,559 -> 1,527,722 | 542,111 -> 561,646 (1 ep) | 233,216 -> 160,283 | 5.8 -> **5.1** | 4.5 -> 3.8 | 446,007 -> 446,007 | 196.5 -> 196.5 |
| #164 VOID | TTIBS_1_0 | 404,781 -> 398,885 | 43,531 -> 47,617 (1 ep) | 35,957 -> 35,306 | 17.3 -> **15.6** | 15.7 -> 14.1 | 71,256 -> 71,256 | 38.1 -> 38.1 |
| #165 VOID | TTIBS_1_0 | 404,781 -> 398,885 | 43,531 -> 47,617 (1 ep) | 35,957 -> 35,306 | 17.3 -> **15.6** | 15.7 -> 14.1 | 71,256 -> 71,256 | 38.1 -> 38.1 |
| #167 VOID | TTIBS_1_0 | 383,448 -> 362,488 | 56,919 -> 56,919 (1 ep) | 32,610 -> 35,820 | 12.6 -> **11.9** | 15.5 -> 12.2 | 35,083 -> 35,083 | 12.3 -> 12.3 |
| #168 VOID | TTIBS_1_0 | 422,748 -> 412,713 | 46,976 -> 51,292 (1 ep) | 35,234 -> 34,736 | 16.8 -> **15.0** | 14.6 -> 13.0 | 87,936 -> 87,936 | 39.2 -> 39.2 |
| #169 VOID | TTIBS_1_0 | 313,070 -> 298,295 | 67,855 -> 67,855 (1 ep) | 40,469 -> 39,932 | 13.1 -> **12.5** | 16.8 -> 15.2 | -8,605 -> -8,605 | -3.8 -> -3.8 |
| #170 VOID | TTIBS_1_0 | 426,665 -> 416,590 | 46,755 -> 51,105 (1 ep) | 35,158 -> 34,677 | 17.0 -> **15.2** | 17.0 -> 15.1 | 27,270 -> 27,270 | 18.2 -> 18.2 |
| #174 VOID | TTIBS_1_0 | 426,665 -> 416,590 | 46,755 -> 51,105 (1 ep) | 35,158 -> 34,677 | 17.0 -> **15.2** | 17.0 -> 15.1 | 27,270 -> 27,270 | 18.2 -> 18.2 |
| #201 VOID | TTIBS_1_0 | 419,288 -> 409,288 | 47,171 -> 51,457 (1 ep) | 35,301 -> 34,788 | 16.6 -> **14.8** | 16.5 -> 14.8 | 26,865 -> 26,865 | 17.9 -> 17.9 |
| #291 | TTIBS_1_1 | 298,325 -> 302,571 | 65,176 -> 65,176 (1 ep) | 36,372 -> 36,689 | 8.5 -> **8.7** | 14.4 -> 16.7 | -47,911 -> -47,911 | -22.1 -> -22.1 |
| #300 | TTIBS_1_3 | 393,623 -> 385,776 | 55,435 -> 55,435 (1 ep) | 37,360 -> 37,235 | 13.2 -> **13.0** | 15.6 -> 15.2 | 16,499 -> 16,499 | 8.9 -> 8.9 |
| #307 | NQDIP_1_0 | 479,321 -> 476,137 | 44,824 -> 57,970 (1 ep) | 35,157 -> 39,965 | 19.8 -> **15.2** | 20.2 -> 15.5 | 20,938 -> 19,822 | 52.4 -> 37.0 |
| #315 | NQDIP_1_1 | 618,762 -> 649,849 | 44,897 -> 54,963 | 42,898 -> 47,225 | 25.5 -> **21.9** | 26.6 -> 22.3 | 13,759 -> 27,255 | 27.6 -> 76.9 |
| #329 | GAPGO_TRAVEL_1_0 | 173,683 -> 187,548 | 47,814 -> 47,814 (1 ep) | 25,997 -> 25,627 | 6.7 -> **7.3** | 14.0 -> 16.2 | -15,923 -> -15,923 | -10.0 -> -10.0 |
| #330 | GAPGO_1_0 | 166,366 -> 182,036 | 71,625 -> 65,585 (1 ep) | 24,875 -> 23,119 | 4.3 -> **5.2** | 12.4 -> 16.4 | -39,179 -> -39,179 | -21.9 -> -21.9 |
| #399 | GAPGO_1_0 | 166,366 -> 182,036 | 71,625 -> 65,585 (1 ep) | 24,875 -> 23,119 | 4.3 -> **5.2** | 12.4 -> 16.4 | -39,179 -> -39,179 | -21.9 -> -21.9 |
| #400 | NQDIP_1_0 | 506,519 -> 511,182 | 48,820 -> 52,397 | 41,997 -> 46,284 | 19.2 -> **18.1** | 20.5 -> 19.4 | 31,888 -> 30,169 | 10.8 -> 9.3 |
| #401 | NQDIP_1_1 | 666,980 -> 650,913 | 53,925 -> 77,381 (1 ep) | 44,568 -> 53,804 | 22.9 -> **15.6** | 23.3 -> 15.5 | 71,446 -> 83,692 | 43.0 -> 45.0 |
| #423 | NQDIP_1_0 | 585,617 -> 602,378 | 36,497 -> 40,262 | 31,382 -> 33,794 | 29.7 -> **27.7** | 30.3 -> 27.9 | 25,284 -> 32,941 | 60.5 -> 83.6 |
| #424 | NQDIP_1_1 | 1,116,128 -> 1,121,941 | 116,916 -> 98,295 | 77,322 -> 79,175 | 17.7 -> **21.1** | 17.6 -> 20.8 | 75,980 -> 86,026 | 106.6 -> 142.5 |
| #425 | NQDIP_1_0 | 366,126 -> 382,754 | 54,016 -> 68,714 (1 ep) | 34,296 -> 38,581 | 12.5 -> **10.3** | 12.5 -> 10.2 | 24,874 -> 27,516 | 66.9 -> 79.6 |

- **VOID** = TTIBS 1.0 with `fill_mode='close'`, the documented look-ahead. These are restated for completeness only.
- **Exact duplicates** (same settings and window): #164 = #165, #170 = #174, #330 = #399.
- **RSIDIV #163** stays void as leveraged buy-and-hold (AUDIT_RSIDIV163).

## DIP: saved vs 1.2/1.3 twin vs PURE (FULL)

| run | saved net / DD / ROC | twin net / DD / ROC | PURE net / DD / ROC | trades touching a switch: saved / twin / pure |
|---|---|---|---|---|
| #307 NQ | 479,321 / 44,824 / 19.8 | 487,450 / 57,970 / 15.6 | 476,137 / 57,970 / 15.2 | 118 ($28,869) / 126 ($16,453) / 104 ($-6,054) |
| #315 NQ | 618,762 / 44,897 / 25.5 | 651,018 / 54,963 / 21.9 | 649,849 / 54,963 / 21.9 | 135 ($25,240) / 142 ($20,116) / 123 ($14,107) |
| #400 NQ | 506,519 / 48,820 / 19.2 | 510,369 / 52,397 / 18.0 | 511,182 / 52,397 / 18.1 | 130 ($10,612) / 137 ($9,226) / 118 ($4,781) |
| #401 NQ | 666,980 / 53,925 / 22.9 | 648,648 / 74,813 / 16.0 | 650,913 / 77,381 / 15.6 | 157 ($-11,227) / 163 ($-4,166) / 140 ($-18,723) |
| #423 NQ | 585,617 / 36,497 / 29.7 | 600,514 / 39,458 / 28.2 | 602,378 / 40,262 / 27.7 | 121 ($48,806) / 130 ($51,751) / 110 ($41,816) |
| #424 NQ | 1,116,128 / 116,916 / 17.7 | 1,121,440 / 97,503 / 21.3 | 1,121,941 / 98,295 / 21.1 | 265 ($11,623) / 294 ($6,044) / 234 ($4,903) |
| #425 ES | 366,126 / 54,016 / 12.5 | 383,911 / 66,592 / 10.7 | 382,754 / 68,714 / 10.3 | 112 ($-29,995) / 123 ($-2,217) / 109 ($-11,898) |

**#424 (MANAGER #62), saved / 1.3 / PURE:**
- Trades: 3,431 / 3,444 / 3,404.
- Net: $1,116,128 / $1,121,440 / $1,121,941.
- Worst DD: $116,916 (1 episode) / $97,503 / $98,295.
- DD5: $77,322 / $76,749 / $79,175.
- ROC: 17.7 / 21.3 / 21.1.
- WF window (2016-07-18 .. 2025-08-23) ROC: 20.6 / 24.6 / 24.0.
- LB year: $75,980 / $80,725 / $86,026, ROC 106.6 / 133.7 / 142.5.
- Trades touching a switch: 265 ($11.6k) / 294 ($6.0k) / 234 ($4.9k).
- **The roll fix alone does the whole move.** Allowing roll-day fills (1.3) adds 40 trades and changes net by -$0.5k and the worst DD by -$0.8k.

## Verification (TTM, independent code path; MANAGER #65: status VERIFIED)

TTM read the settings from Firestore and did its own switch mapping from switch_sec. It rebuilt the SAVED source with two text edits, and its control reproduced the saved runs trade for trade.
- **#300 TTIBS:** exact match. 703 trades, $385,776, worst DD $55,435, DD5 $37,235.
- **#424 and #401 DIP:** every trade the two lines share matches to the cent. The non-shared trades sit within 60 sessions of a switch (83% / 86%).
- **Definition (MANAGER #65):** the restated figure is the ADJUSTED-SIGNAL pure line above. A lookback that spans a switch on raw prices still carries the roll step inside its indicator for about 60 sessions.
- **Sensitivity, raw-signal pure line (TTM):**
  - #424: 3,423 trades, $1,124,059, worst DD $102,917, DD5 $82,200, ROC 20.2 (adjusted 21.1), LB $92,954.
  - #401: 1,382 trades, $656,423, worst DD $77,381 (the same), DD5 $52,221, ROC 15.7 (adjusted 15.6).
  - The direction and size of every restatement hold under both definitions.

## Crowns and rankings

Ranked on FULL ROC, the one window every run in a family shares. Lockbox years differ between runs (12 or 24 months), so LB is not a ranking window.

### DIP NQ
- **Saved order:** #423 29.7 > #315 25.5 > #401 22.9 > #307 19.8 > #400 19.2 > #424 17.7.
- **True order:** #423 27.7 > #315 21.9 > #424 21.1 > #400 18.1 > #401 15.6 > #307 15.2.
- **Top unchanged.** #423's true twin is the clean run #433 (28.2, identical trades).

- **Clean DIP 1.3 #434 (25.1) now sits 2nd**, ahead of #315. Saved, #315 led it at 25.5.

- **Movers:** #424 rises from last to 3rd. #401 falls from 3rd to 5th: its worst DD grows from $53.9k to $77.4k and becomes one episode. #307 falls to last: DD $44.8k -> $58.0k.
- **DIP ES:** #425 12.5 -> 10.3 (its twin is the clean run #432, 10.7). Clean ES 1.3 #452 (14.2) stays the ES lead.

### TTIBS
- **Honest runs:** #300 13.2 -> 13.0 stays ahead of #291 8.5 -> 8.7.
- **Pre-window flip:** on the pre window alone, #291 (14.4 -> 16.7) passes #300 (15.6 -> 15.2).
  - #291's LB is still -$47.9k, so #300 remains the TTIBS lead. The family is parked.
- **Void runs:** all 9 lose 0.6-1.8 FULL ROC; net falls 1.4-5.5%.
- **LB years:** unchanged on every TTIBS run (the detector found the true rolls in that year).

### GAPGO
- **Detector false flags cost GAPGO profit.** Net +8-9%, FULL ROC #329 6.7 -> 7.3, #330 / #399 4.3 -> 5.2.
- **Pre-window flip:** #330 / #399 (12.4 -> 16.4) pass #329 (14.0 -> 16.2). It is a near-tie.
- **Unchanged:** the FULL order and the LB years (all still losing). The family stays dead.

### RSIDIV #163
- Net $1.67M -> $1.53M, ROC 5.8 -> 5.1. It stays void.

## Read

- **No crown flips.** The DIP NQ lead (#423 / #433), DIP ES (#452), TTIBS (#300) and GAPGO (#329) all hold.
- **DIP old runs mostly read too good on drawdown.** 6 of 7 get deeper worst DDs on the true table, because the detector had dropped real crash gaps.
  - On the true table the worst episode is Feb-Apr 2020 for #307, #315, #400, #401 and #425 (saved, it was 2022 or 2011-12 for three of them). #423's is now 2018.
  - #424 is the exception: its worst episode (2022) loses two fake favourable gaps (2022-03-09, 2022-12-13).
- **No lockbox sign changes.** Not one run's lockbox net changes sign.
- **Rule for re-use:** any re-use of these 22 should quote the true-table numbers above, not the saved ones.

Files: `C:\EdgeLog\_anatomy_cache\restate_roll\`:
- scripts: restate_batch.py, restate_dip_pure.py, summarize.py;
- results: restate_*.json, dippure_*.json, clean_dip_stats.json;
- trade lists: dip<id>_{saved,twin,pure}_trades.csv.
